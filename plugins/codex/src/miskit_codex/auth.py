from dataclasses import dataclass
from pathlib import Path

from miskit_codex.oauth import OAuthConfig, OAuthSession, extract_jwt_claim


_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
_AUTHORIZE_URL = "https://auth.openai.com/oauth/authorize"
_TOKEN_URL = "https://auth.openai.com/oauth/token"
_REDIRECT_URI = "http://localhost:1455/auth/callback"
_SCOPE = "openid profile email offline_access"
_JWT_AUTH_CLAIM = "https://api.openai.com/auth"
_JWT_ACCOUNT_ID_FIELD = "chatgpt_account_id"


@dataclass
class CodexToken:
    access: str
    refresh: str
    expires: int
    account_id: str


def _token_path():
    return Path.home() / ".miskit" / "auth" / "codex.json"


def _make_session():
    return OAuthSession(OAuthConfig(
        client_id=_CLIENT_ID,
        authorize_url=_AUTHORIZE_URL,
        token_url=_TOKEN_URL,
        redirect_uri=_REDIRECT_URI,
        scope=_SCOPE,
        token_path=_token_path(),
        extra_authorize_params={
            "id_token_add_organizations": "true",
            "codex_cli_simplified_flow": "true",
            "originator": "miskit",
        },
    ))


def get_codex_token():
    session = _make_session()
    token = session.get_token()
    account_id = extract_jwt_claim(token.access, _JWT_AUTH_CLAIM, _JWT_ACCOUNT_ID_FIELD) or ""
    if not account_id:
        raise ValueError("Codex token has no account id. Run: miskit login codex")
    return CodexToken(token.access, token.refresh, token.expires, account_id)


def login_codex(write=print, read=input):
    session = _make_session()
    token = session.login(write=write, read=read)
    account_id = extract_jwt_claim(token.access, _JWT_AUTH_CLAIM, _JWT_ACCOUNT_ID_FIELD) or ""
    if not account_id:
        raise ValueError("Login succeeded but the access token had no ChatGPT account id.")
    write(f"Authenticated with Codex: {account_id}")
    return CodexToken(token.access, token.refresh, token.expires, account_id)
