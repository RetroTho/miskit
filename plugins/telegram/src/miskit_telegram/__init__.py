import asyncio
import json
import re
import time
import urllib.error
import urllib.request

from miskit.channel import Channel

_TELEGRAM_API = "https://api.telegram.org"
_MAX_MESSAGE_LENGTH = 4096
_HTTP_TIMEOUT_SECONDS = 120  # must exceed the max poll timeout (50s) plus network overhead
_MIN_RETRY_SLEEP = 1.0
_MAX_RETRY_SLEEP = 120.0
_DEFAULT_RETRY_AFTER = 5.0


class TelegramRetryAfter(Exception):
    def __init__(self, seconds):
        super().__init__(f"retry after {seconds}s")
        self.seconds = seconds


class TelegramTransient(Exception):
    pass


class TelegramFatal(Exception):
    pass


def _retry_after(body):
    params = body.get("parameters")
    if isinstance(params, dict):
        value = params.get("retry_after")
        if isinstance(value, (int, float)) and value > 0:
            return float(value)

    match = re.search(r"retry after (\d+)", str(body.get("description", "")), re.IGNORECASE)
    if match:
        return float(match.group(1))

    return None


def _post_attempt(url, payload):
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=_HTTP_TIMEOUT_SECONDS) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        if error.code == 429:
            try:
                parsed = json.loads(detail)
            except json.JSONDecodeError:
                parsed = {}
            raise TelegramRetryAfter(_retry_after(parsed) or _DEFAULT_RETRY_AFTER) from error
        if error.code >= 500:
            raise TelegramTransient(f"HTTP {error.code}: {detail}") from error
        raise TelegramFatal(f"Telegram HTTP error: {error.code} {detail}") from error
    except urllib.error.URLError as error:
        raise TelegramTransient(str(error)) from error

    try:
        body = json.loads(raw)
    except json.JSONDecodeError as error:
        raise TelegramTransient("Telegram returned invalid JSON.") from error

    if body.get("ok"):
        return body.get("result")

    description = str(body.get("description", "Telegram request failed."))
    code = body.get("error_code")

    if code == 429:
        raise TelegramRetryAfter(_retry_after(body) or _DEFAULT_RETRY_AFTER)
    if code == 401:
        raise TelegramFatal(description)
    if code == 409:
        raise TelegramFatal(
            f"{description} (If you used a webhook before, call deleteWebhook and try again.)"
        )
    if isinstance(code, int) and code >= 500:
        raise TelegramTransient(description)
    if isinstance(code, int) and code < 500:
        raise TelegramFatal(description)

    raise TelegramFatal(description)


def _post(url, payload, log=None):
    backoff = _MIN_RETRY_SLEEP
    while True:
        try:
            return _post_attempt(url, payload)
        except TelegramRetryAfter as exc:
            wait = max(_MIN_RETRY_SLEEP, min(exc.seconds, _MAX_RETRY_SLEEP))
            if log is not None:
                log(f"Telegram rate limit: waiting {wait:.0f}s, then retrying.")
            time.sleep(wait)
            backoff = _MIN_RETRY_SLEEP
        except TelegramTransient as exc:
            if log is not None:
                log(f"Telegram unreachable ({exc}); retrying in {backoff:.0f}s.")
            time.sleep(backoff)
            backoff = min(backoff * 2, _MAX_RETRY_SLEEP)
        except TelegramFatal as exc:
            raise RuntimeError(str(exc)) from exc


class TelegramBotClient:
    def __init__(self, token, log=None):
        self._base = f"{_TELEGRAM_API}/bot{token}"
        self._log = log

    def get_updates(self, offset, timeout_seconds):
        result = _post(
            f"{self._base}/getUpdates",
            {"offset": offset, "timeout": timeout_seconds},
            log=self._log,
        )
        if not isinstance(result, list):
            return [], offset

        updates = [item for item in result if isinstance(item, dict)]
        ids = [uid for uid in (u.get("update_id") for u in updates) if isinstance(uid, int)]
        next_offset = max(ids) + 1 if ids else offset

        return updates, next_offset

    def send_message(self, chat_id, text):
        _post(
            f"{self._base}/sendMessage",
            {"chat_id": chat_id, "text": text, "disable_web_page_preview": True},
            log=self._log,
        )


def _text_from_update(update):
    for key in ("message", "channel_post", "edited_message", "edited_channel_post"):
        part = update.get(key)
        if not isinstance(part, dict):
            continue

        text = part.get("text") or part.get("caption")
        if not isinstance(text, str) or not text.strip():
            continue

        chat = part.get("chat")
        if not isinstance(chat, dict):
            continue

        chat_id = chat.get("id")
        if chat_id is None:
            continue

        return str(chat_id), text.strip()

    return None, None


def _chunks(text, max_length):
    pieces = []
    while text:
        pieces.append(text[:max_length])
        text = text[max_length:]
    return pieces


class TelegramChannel(Channel):
    def __init__(self, token, chat_id, poll_timeout=30, client=None, write=print):
        self._chat_id = chat_id
        self._poll_timeout = poll_timeout
        self._write = write
        self._client = client or TelegramBotClient(token, log=self._note)

    def _note(self, line):
        self._write(f"[telegram] {line}")

    async def _process_batch(self, runner, offset):
        updates, next_offset = await asyncio.to_thread(
            self._client.get_updates, offset, self._poll_timeout
        )

        for update in updates:
            chat_id, text = _text_from_update(update)
            if chat_id is None or chat_id != self._chat_id:
                continue

            try:
                reply = await runner.chat(text)
                await self.send(reply.content)
            except Exception as exc:
                self._note(f"could not answer message: {exc}")
                try:
                    await self.send(f"Sorry, something went wrong: {exc}")
                except Exception as send_exc:
                    self._note(f"could not send error reply: {send_exc}")

        return next_offset

    async def run(self, runner):
        offset = 0
        self._write(f"Miskit Telegram channel watching chat {self._chat_id}. Press Ctrl-C to stop.")

        while True:
            offset = await self._process_batch(runner, offset)

    async def send(self, content):
        for part in _chunks(content, _MAX_MESSAGE_LENGTH):
            await asyncio.to_thread(self._client.send_message, self._chat_id, part)


def create_channel(config):
    token = str(config.get("token", "")).strip()
    if not token:
        raise ValueError("channel.token is required for telegram")

    chat_id_raw = config.get("chatId")
    if chat_id_raw is None or str(chat_id_raw).strip() == "":
        raise ValueError("channel.chatId is required for telegram")

    poll_raw = config.get("pollTimeout", 30)
    try:
        poll_timeout = int(poll_raw)
    except (TypeError, ValueError) as error:
        raise ValueError("channel.pollTimeout must be an integer") from error

    if poll_timeout < 1 or poll_timeout > 50:
        raise ValueError("channel.pollTimeout must be between 1 and 50 (seconds)")

    return TelegramChannel(token, str(chat_id_raw).strip(), poll_timeout=poll_timeout)
