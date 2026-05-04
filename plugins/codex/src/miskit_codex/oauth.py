import base64
import fcntl
import hashlib
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path


def _base64url(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _decode_base64url(text):
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)


def new_pkce_pair():
    verifier = _base64url(os.urandom(32))
    digest = hashlib.sha256(verifier.encode("utf-8")).digest()
    challenge = _base64url(digest)
    return verifier, challenge


def new_state():
    return _base64url(os.urandom(16))


def parse_pasted_redirect(raw):
    value = raw.strip()
    if not value:
        return None, None

    try:
        parsed = urllib.parse.urlparse(value)
        query = urllib.parse.parse_qs(parsed.query)
        code = query.get("code", [None])[0]
        state = query.get("state", [None])[0]
        if code:
            return code, state
    except Exception:
        pass

    if "code=" in value:
        query = urllib.parse.parse_qs(value)
        return query.get("code", [None])[0], query.get("state", [None])[0]

    return value, None


def extract_jwt_claim(access_token, claim_path, field):
    parts = access_token.split(".")
    if len(parts) != 3:
        raise ValueError("Access token is not a JWT (expected three dot-separated segments).")

    payload = json.loads(_decode_base64url(parts[1]).decode("utf-8"))
    auth_block = payload.get(claim_path) or {}
    value = auth_block.get(field)
    return str(value) if value is not None else None


def _parse_token_response(payload):
    access = payload.get("access_token")
    refresh = payload.get("refresh_token")
    expires_in = payload.get("expires_in")
    if not access or not refresh or expires_in is None:
        raise RuntimeError("Token response missing access_token, refresh_token, or expires_in.")
    try:
        seconds = int(expires_in)
    except (TypeError, ValueError) as error:
        raise RuntimeError("Token response had a non-numeric expires_in.") from error
    return str(access), str(refresh), seconds


def _post_form(url, fields, timeout=60.0):
    body = urllib.parse.urlencode(fields).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        text = response.read().decode("utf-8", errors="replace")
    return json.loads(text)


def _post_form_with_error_detail(url, fields, timeout=60.0):
    try:
        return _post_form(url, fields, timeout=timeout)
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Token request failed (HTTP {error.code}): {detail}") from error


def _load_token_json(path):
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _save_token_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


@dataclass
class OAuthConfig:
    client_id: str
    authorize_url: str
    token_url: str
    redirect_uri: str
    scope: str
    token_path: Path
    extra_authorize_params: dict | None = None


@dataclass
class OAuthToken:
    access: str
    refresh: str
    expires: int


class _TokenFileLock:
    def __init__(self, path):
        self._lock_path = path.with_suffix(path.suffix + ".lock")
        self._lock_path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = None

    def __enter__(self):
        self._handle = open(self._lock_path, "a+", encoding="utf-8")
        try:
            fcntl.flock(self._handle.fileno(), fcntl.LOCK_EX)
        except Exception:
            pass
        return self

    def __exit__(self, *_):
        try:
            fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        self._handle.close()


class OAuthSession:
    def __init__(self, config):
        self.config = config

    def get_token(self, min_ttl_seconds=60):
        data = _load_token_json(self.config.token_path)
        if not data:
            raise ValueError("No saved OAuth token. Log in first.")

        token = self._dict_to_token(data)
        now_ms = int(time.time() * 1000)
        if token.expires - now_ms > min_ttl_seconds * 1000:
            return token

        with _TokenFileLock(self.config.token_path):
            refreshed_disk = _load_token_json(self.config.token_path)
            if refreshed_disk:
                token = self._dict_to_token(refreshed_disk)
                now_ms = int(time.time() * 1000)
                if token.expires - now_ms > min_ttl_seconds * 1000:
                    return token

            try:
                refreshed = self._refresh_access(token.refresh)
                self._save(refreshed)
                return refreshed
            except Exception as first_error:
                latest = _load_token_json(self.config.token_path)
                if latest:
                    token2 = self._dict_to_token(latest)
                    now_ms = int(time.time() * 1000)
                    if token2.expires - now_ms > 0:
                        return token2
                raise ValueError("Could not refresh OAuth token. Log in first.") from first_error

    def login(self, write=print, read=input):
        try:
            return self.get_token()
        except ValueError:
            pass

        verifier, challenge = new_pkce_pair()
        state = new_state()
        url = self._authorization_url(state, challenge)

        write("Open this URL in your browser to sign in:")
        write(url)

        pasted = read("Paste the redirect URL or authorization code here: ")
        code, pasted_state = parse_pasted_redirect(pasted)
        if pasted_state and pasted_state != state:
            raise ValueError("State mismatch: use the redirect link from this login attempt only.")
        if not code:
            raise RuntimeError("No authorization code received.")

        write("Exchanging authorization code for tokens...")
        token = self._exchange_code(code, verifier)
        self._save(token)
        return token

    def _authorization_url(self, state, challenge):
        params = {
            "response_type": "code",
            "client_id": self.config.client_id,
            "redirect_uri": self.config.redirect_uri,
            "scope": self.config.scope,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": state,
            **(self.config.extra_authorize_params or {}),
        }
        return f"{self.config.authorize_url}?{urllib.parse.urlencode(params)}"

    def _exchange_code(self, code, verifier):
        payload = _post_form_with_error_detail(
            self.config.token_url,
            {
                "grant_type": "authorization_code",
                "client_id": self.config.client_id,
                "code": code,
                "code_verifier": verifier,
                "redirect_uri": self.config.redirect_uri,
            },
        )
        access, refresh, expires_in = _parse_token_response(payload)
        expires_ms = int(time.time() * 1000) + expires_in * 1000
        return OAuthToken(access=access, refresh=refresh, expires=expires_ms)

    def _refresh_access(self, refresh_token):
        payload = _post_form_with_error_detail(
            self.config.token_url,
            {
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": self.config.client_id,
            },
        )
        access, refresh, expires_in = _parse_token_response(payload)
        expires_ms = int(time.time() * 1000) + expires_in * 1000
        return OAuthToken(access=access, refresh=refresh, expires=expires_ms)

    def _save(self, token):
        _save_token_json(
            self.config.token_path,
            {"access": token.access, "refresh": token.refresh, "expires": token.expires},
        )

    def _dict_to_token(self, data):
        try:
            access = str(data["access"])
            refresh = str(data["refresh"])
            expires = int(data["expires"])
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("Saved OAuth token file is damaged. Log in again.") from error
        return OAuthToken(access=access, refresh=refresh, expires=expires)
