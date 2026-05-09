import asyncio
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from miskit.channel import Channel
from miskit.message import Message


@dataclass
class Attachment:
    path: str
    mime_type: str


@dataclass
class IncomingMessage:
    rowid: int
    text: str
    attachments: list


class MessagesDatabase:
    def __init__(self, path=None):
        if path is None:
            path = Path.home() / "Library" / "Messages" / "chat.db"
        self.path = Path(path).expanduser()

    def latest_rowid(self, chat_guid):
        with closing(self.connect()) as connection:
            row = connection.execute(
                """
                select coalesce(max(message.ROWID), 0) as rowid
                from message
                join chat_message_join on chat_message_join.message_id = message.ROWID
                join chat on chat.ROWID = chat_message_join.chat_id
                where chat.guid = ?
                """,
                (chat_guid,),
            ).fetchone()
        return int(row["rowid"])

    def chat_guid(self, recipient):
        with closing(self.connect()) as connection:
            row = connection.execute(
                "select guid from chat where guid = ? limit 1",
                (recipient,),
            ).fetchone()
            if row is not None:
                return row["guid"]

            row = connection.execute(
                """
                select chat.guid as guid
                from chat
                join chat_handle_join on chat_handle_join.chat_id = chat.ROWID
                join handle on handle.ROWID = chat_handle_join.handle_id
                where handle.id = ?
                  and (
                    select count(*)
                    from chat_handle_join as members
                    where members.chat_id = chat.ROWID
                  ) = 1
                order by chat.ROWID desc
                limit 1
                """,
                (recipient,),
            ).fetchone()

            if row is None:
                row = connection.execute(
                    """
                    select guid
                    from chat
                    where chat_identifier = ?
                    order by ROWID desc
                    limit 1
                    """,
                    (recipient,),
                ).fetchone()
        if row is None:
            return None
        return row["guid"]

    def incoming_after(self, chat_guid, rowid):
        with closing(self.connect()) as connection:
            rows = connection.execute(
                """
                select
                    message.ROWID as rowid,
                    message.text as text,
                    attachment.filename as attachment_path,
                    attachment.mime_type as attachment_mime_type
                from message
                join chat_message_join on chat_message_join.message_id = message.ROWID
                join chat on chat.ROWID = chat_message_join.chat_id
                left join message_attachment_join on message_attachment_join.message_id = message.ROWID
                left join attachment on attachment.ROWID = message_attachment_join.attachment_id
                where chat.guid = ?
                  and message.ROWID > ?
                  and message.is_from_me = 0
                  and (
                    (message.text is not null and message.text != '')
                    or attachment.filename is not null
                  )
                order by message.ROWID
                """,
                (chat_guid, rowid),
            ).fetchall()

        return _group_messages(rows)

    def connect(self):
        database_uri = "file:" + quote(str(self.path), safe="/") + "?mode=ro"
        connection = sqlite3.connect(database_uri, uri=True)
        connection.row_factory = sqlite3.Row
        return connection


def _group_messages(rows):
    messages = {}

    for row in rows:
        rowid = int(row["rowid"])

        if rowid not in messages:
            messages[rowid] = IncomingMessage(
                rowid=rowid,
                text=row["text"] or "",
                attachments=[],
            )

        path = row["attachment_path"]
        if path:
            messages[rowid].attachments.append(
                Attachment(path=path, mime_type=row["attachment_mime_type"] or "")
            )

    return list(messages.values())


def _normalize_attachment_path(path):
    if not path:
        return None
    if path.startswith("file://"):
        path = path[7:]
    return Path(path).expanduser()


_SEND_SCRIPT = Path(__file__).parent / "send.applescript"


class MessagesApp:
    async def send(self, chat_guid, content):
        process = await asyncio.create_subprocess_exec(
            "osascript", str(_SEND_SCRIPT),
            chat_guid,
            content,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            output = stderr.decode("utf-8", errors="replace").strip()
            if not output:
                output = stdout.decode("utf-8", errors="replace").strip()
            raise RuntimeError(output or "Messages failed to send the iMessage.")


class IMessageChannel(Channel):
    def __init__(self, recipient, database=None, sender=None, image_store=None, poll_seconds=2, write=print):
        self.recipient = recipient
        self.database = database or MessagesDatabase()
        self.sender = sender or MessagesApp()
        self.image_store = image_store
        self.poll_seconds = poll_seconds
        self.write = write
        self.chat_guid = None
        self.last_rowid = None

    def _note(self, line):
        self.write(f"[imessage] {line}")

    def start(self):
        self.chat_guid = self.database.chat_guid(self.recipient)
        if self.chat_guid is None:
            raise ValueError(
                "No iMessage chat found for this recipient. "
                "Send or receive a message with this recipient first."
            )
        self.last_rowid = self.database.latest_rowid(self.chat_guid)

    async def run(self, runner):
        self.start()
        self.write(f"Miskit iMessage channel watching {self.recipient}. Press Ctrl-C to stop.")

        while True:
            await self.run_pending(runner)
            await asyncio.sleep(self.poll_seconds)

    async def run_pending(self, runner):
        if self.last_rowid is None:
            self.start()

        for incoming in self.database.incoming_after(self.chat_guid, self.last_rowid):
            self.last_rowid = incoming.rowid
            message = self._build_message(incoming)
            if message is None:
                continue
            self._note(f"Received: {incoming.text!r}")
            reply = await runner.chat(message)
            await self.send(reply.content)

    def _build_message(self, incoming):
        text = incoming.text.strip()
        images = self._save_attachments(incoming.attachments)

        if not text and not images:
            return None

        if not images:
            return text

        content = []
        if text:
            content.append({"type": "text", "text": text})
        for image in images:
            content.append({"type": "image", "path": image["path"], "mime_type": image["mime_type"]})

        stored_parts = [text] if text else []
        for _ in images:
            stored_parts.append("[Image]")

        return Message("user", content, stored_content="\n".join(stored_parts))

    def _save_attachments(self, attachments):
        if self.image_store is None:
            return []

        images = []
        for attachment in attachments:
            path = _normalize_attachment_path(attachment.path)
            if path is None or not path.exists():
                continue
            if not self.image_store.is_supported_image(
                mime_type=attachment.mime_type, filename=path.name,
            ):
                continue
            metadata = self.image_store.copy_file(path, mime_type=attachment.mime_type)
            images.append(metadata)

        return images

    async def send(self, content):
        self._note(f"Sending to {self.recipient} ({len(content)} chars).")
        await self.sender.send(self.chat_guid, content)
        self._note("Sent.")


def create_channel(config, image_store=None):
    recipient = str(config.get("recipient", "")).strip()
    if not recipient:
        raise ValueError("channel.recipient is required for imessage")

    try:
        poll_seconds = float(config.get("pollSeconds", 2))
    except (TypeError, ValueError) as error:
        raise ValueError("channel.pollSeconds must be a number") from error

    if poll_seconds <= 0:
        raise ValueError("channel.pollSeconds must be greater than 0")

    database_path = config.get("database")
    database = MessagesDatabase(database_path) if database_path else None
    return IMessageChannel(recipient, database=database, image_store=image_store, poll_seconds=poll_seconds)
