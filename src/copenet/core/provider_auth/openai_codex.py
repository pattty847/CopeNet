from __future__ import annotations

import base64
import hashlib
import json
import secrets
import threading
import time
import webbrowser
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib import error, parse, request

from copenet._paths import default_provider_auth_dir
from copenet.core.sessions.session_store import utc_now_iso

from .store import ProviderAuthProfile, ProviderAuthStore

OPENAI_CODEX_PROVIDER_ID = "openai-codex"
OPENAI_CODEX_PROFILE_ID = "openai-codex:default"
OPENAI_CODEX_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
OPENAI_CODEX_SCOPES = ("openid", "profile", "email", "offline_access")
OPENAI_CODEX_AUTH_BASE_URL = "https://auth.openai.com"
OPENAI_CODEX_REDIRECT_URI = "http://localhost:1455/auth/callback"
OPENAI_CODEX_REFRESH_MARGIN_MS = 30_000
OPENAI_CODEX_ORIGINATOR = "copenet"


@dataclass(frozen=True)
class PendingOpenAICodexLogin:
    login_id: str
    authorize_url: str
    redirect_uri: str
    state: str
    code_verifier: str
    created_at: float


class OpenAICodexAuthService:
    def __init__(self, store: ProviderAuthStore | None = None) -> None:
        auth_dir = default_provider_auth_dir()
        self._store = store or ProviderAuthStore(auth_dir / f"{OPENAI_CODEX_PROVIDER_ID}.json")
        self._pending: dict[str, PendingOpenAICodexLogin] = {}

    @property
    def store(self) -> ProviderAuthStore:
        return self._store

    def status(self) -> dict[str, object]:
        profile = self._store.load()
        now_ms = int(time.time() * 1000)
        authenticated = bool(profile and profile.access_token and profile.refresh_token)
        expired = bool(profile and profile.expires_at <= now_ms)
        return {
            "provider": OPENAI_CODEX_PROVIDER_ID,
            "profileId": OPENAI_CODEX_PROFILE_ID,
            "requiresAuth": True,
            "authType": "oauth",
            "authenticated": authenticated,
            "expired": expired,
            "accountId": profile.account_id if profile else None,
            "expiresAt": profile.expires_at if profile else None,
            "scopes": list(profile.scopes) if profile else list(OPENAI_CODEX_SCOPES),
            "storePath": str(self._store.path),
        }

    def begin_login(self, redirect_uri: str | None = None) -> dict[str, object]:
        redirect = (redirect_uri or OPENAI_CODEX_REDIRECT_URI).strip() or OPENAI_CODEX_REDIRECT_URI
        code_verifier = _generate_code_verifier()
        code_challenge = _build_code_challenge(code_verifier)
        state = secrets.token_urlsafe(24)
        login_id = secrets.token_urlsafe(18)
        authorize_url = _build_authorize_url(
            redirect_uri=redirect,
            state=state,
            code_challenge=code_challenge,
        )
        pending = PendingOpenAICodexLogin(
            login_id=login_id,
            authorize_url=authorize_url,
            redirect_uri=redirect,
            state=state,
            code_verifier=code_verifier,
            created_at=time.time(),
        )
        self._pending[login_id] = pending
        return {
            "provider": OPENAI_CODEX_PROVIDER_ID,
            "profileId": OPENAI_CODEX_PROFILE_ID,
            "loginToken": login_id,
            "authorizeUrl": authorize_url,
            "redirectUri": redirect,
            "state": state,
        }

    def complete_login(
        self,
        *,
        login_token: str,
        redirect_url: str | None = None,
        code: str | None = None,
        state: str | None = None,
    ) -> dict[str, object]:
        pending = self._pending.get(login_token.strip())
        if pending is None:
            raise ValueError("unknown login token")
        resolved_code = (code or "").strip()
        resolved_state = (state or "").strip()
        if redirect_url:
            parsed = parse.urlparse(redirect_url)
            query = parse.parse_qs(parsed.query)
            resolved_code = resolved_code or str((query.get("code") or [""])[0]).strip()
            resolved_state = resolved_state or str((query.get("state") or [""])[0]).strip()
        if not resolved_code:
            raise ValueError("authorization code is required")
        if resolved_state != pending.state:
            raise ValueError("oauth state mismatch")
        profile = self._exchange_authorization_code(
            code=resolved_code,
            code_verifier=pending.code_verifier,
            redirect_uri=pending.redirect_uri,
        )
        self._save_profile(profile)
        self._pending.pop(login_token.strip(), None)
        status = self.status()
        status["profile"] = profile.to_public_dict()
        return status

    def login_with_browser(self, timeout_sec: float = 300.0, open_browser: bool = True) -> dict[str, object]:
        begun = self.begin_login()
        redirect_uri = str(begun["redirectUri"])
        redirect_url: str | None = None
        if open_browser:
            webbrowser.open(str(begun["authorizeUrl"]))
        try:
            redirect_url = _wait_for_callback_redirect(redirect_uri=redirect_uri, timeout_sec=timeout_sec)
        except OSError:
            redirect_url = None
        if redirect_url is None:
            print("Open the URL below in your browser, then paste the full redirected URL here:\n")
            print(begun["authorizeUrl"])
            redirect_url = input("\nRedirect URL: ").strip()
        return self.complete_login(login_token=str(begun["loginToken"]), redirect_url=redirect_url)

    def logout(self) -> dict[str, object]:
        with self._store.locked():
            self._store.clear()
        return self.status()

    def ensure_valid_profile(self) -> ProviderAuthProfile:
        with self._store.locked():
            profile = self._store.load()
            if profile is None or not profile.access_token or not profile.refresh_token:
                raise RuntimeError(
                    "openai-codex is not authenticated. Run `uv run copenet auth login --provider openai-codex`."
                )
            now_ms = int(time.time() * 1000)
            if profile.expires_at > now_ms + OPENAI_CODEX_REFRESH_MARGIN_MS:
                return profile
            refreshed = self._refresh_profile(profile)
            self._store.save(refreshed)
            return refreshed

    def _exchange_authorization_code(self, *, code: str, code_verifier: str, redirect_uri: str) -> ProviderAuthProfile:
        payload = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": OPENAI_CODEX_CLIENT_ID,
            "code_verifier": code_verifier,
        }
        data = _token_request(payload)
        return _profile_from_token_payload(data)

    def _refresh_profile(self, profile: ProviderAuthProfile) -> ProviderAuthProfile:
        payload = {
            "grant_type": "refresh_token",
            "refresh_token": profile.refresh_token,
            "client_id": OPENAI_CODEX_CLIENT_ID,
        }
        data = _token_request(payload)
        next_profile = _profile_from_token_payload(data, fallback_account_id=profile.account_id)
        return ProviderAuthProfile(
            provider=OPENAI_CODEX_PROVIDER_ID,
            profile_id=OPENAI_CODEX_PROFILE_ID,
            access_token=next_profile.access_token,
            refresh_token=next_profile.refresh_token or profile.refresh_token,
            expires_at=next_profile.expires_at,
            account_id=next_profile.account_id or profile.account_id,
            scopes=next_profile.scopes or profile.scopes,
            updated_at=utc_now_iso(),
        )

    def _save_profile(self, profile: ProviderAuthProfile) -> None:
        with self._store.locked():
            self._store.save(profile)


class _OAuthCallbackHandler(BaseHTTPRequestHandler):
    callback_path = "/auth/callback"
    redirect_url: str | None = None
    event: threading.Event | None = None

    def do_GET(self) -> None:  # noqa: N802
        query = parse.urlsplit(self.path)
        if not query.path.startswith(self.callback_path):
            self.send_response(404)
            self.end_headers()
            return
        redirect = f"http://{self.headers.get('Host')}{self.path}"
        type(self).redirect_url = redirect
        if type(self).event is not None:
            type(self).event.set()
        body = b"CopeNet OpenAI Codex login complete. You can close this tab."
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A003
        return



def _build_authorize_url(*, redirect_uri: str, state: str, code_challenge: str) -> str:
    query = parse.urlencode(
        {
            "client_id": OPENAI_CODEX_CLIENT_ID,
            "redirect_uri": redirect_uri,
            "scope": " ".join(OPENAI_CODEX_SCOPES),
            "response_type": "code",
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "state": state,
            "id_token_add_organizations": "true",
            "codex_cli_simplified_flow": "true",
        }
    )
    return f"{OPENAI_CODEX_AUTH_BASE_URL}/oauth/authorize?{query}"



def _generate_code_verifier() -> str:
    return secrets.token_urlsafe(64)



def _build_code_challenge(code_verifier: str) -> str:
    digest = hashlib.sha256(code_verifier.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")



def _token_request(payload: dict[str, str]) -> dict[str, Any]:
    encoded = parse.urlencode(payload).encode("utf-8")
    req = request.Request(
        f"{OPENAI_CODEX_AUTH_BASE_URL}/oauth/token",
        data=encoded,
        headers=_build_openai_codex_headers(
            content_type="application/x-www-form-urlencoded",
            accept="application/json",
        ),
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=30.0) as response:
            data = json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"openai-codex token exchange failed: {exc.code} {detail or exc.reason}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"openai-codex token exchange failed: {exc.reason}") from exc
    if not isinstance(data, dict):
        raise RuntimeError("openai-codex token exchange returned an invalid response")
    return data



def _decode_jwt_payload(access_token: str) -> dict[str, Any] | None:
    parts = access_token.split(".")
    if len(parts) != 3:
        return None
    try:
        payload = base64.urlsafe_b64decode(parts[1] + "==")
        parsed = json.loads(payload.decode("utf-8"))
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None



def _resolve_account_id(access_token: str) -> str | None:
    payload = _decode_jwt_payload(access_token)
    if not isinstance(payload, dict):
        return None
    auth = payload.get("https://api.openai.com/auth")
    if not isinstance(auth, dict):
        return None
    for key in ("chatgpt_account_id", "chatgpt_account_user_id", "chatgpt_user_id", "user_id"):
        value = str(auth.get(key) or "").strip()
        if value:
            return value
    return None



def _resolve_expiry(access_token: str, expires_in: object) -> int:
    payload = _decode_jwt_payload(access_token)
    if isinstance(payload, dict):
        exp = payload.get("exp")
        if isinstance(exp, int) and exp > 0:
            return exp * 1000
        if isinstance(exp, str) and exp.isdigit():
            return int(exp) * 1000
    seconds = int(expires_in or 0)
    if seconds <= 0:
        seconds = 3600
    return int(time.time() * 1000) + seconds * 1000



def _profile_from_token_payload(data: dict[str, Any], fallback_account_id: str | None = None) -> ProviderAuthProfile:
    access_token = str(data.get("access_token") or "").strip()
    refresh_token = str(data.get("refresh_token") or "").strip()
    if not access_token or not refresh_token:
        raise RuntimeError("openai-codex token response did not include access and refresh tokens")
    scopes = tuple(token for token in str(data.get("scope") or "").split() if token)
    return ProviderAuthProfile(
        provider=OPENAI_CODEX_PROVIDER_ID,
        profile_id=OPENAI_CODEX_PROFILE_ID,
        access_token=access_token,
        refresh_token=refresh_token,
        expires_at=_resolve_expiry(access_token, data.get("expires_in")),
        account_id=_resolve_account_id(access_token) or fallback_account_id,
        scopes=scopes or OPENAI_CODEX_SCOPES,
        updated_at=utc_now_iso(),
    )



def _wait_for_callback_redirect(*, redirect_uri: str, timeout_sec: float) -> str | None:
    parsed = parse.urlparse(redirect_uri)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or not parsed.port:
        raise OSError("redirect URI is not a local HTTP callback")
    event = threading.Event()
    _OAuthCallbackHandler.redirect_url = None
    _OAuthCallbackHandler.event = event
    _OAuthCallbackHandler.callback_path = parsed.path or "/"
    server = HTTPServer((parsed.hostname, parsed.port), _OAuthCallbackHandler)
    server.timeout = 0.2

    def _serve() -> None:
        deadline = time.time() + timeout_sec
        while time.time() < deadline and not event.is_set():
            server.handle_request()

    thread = threading.Thread(target=_serve, daemon=True)
    thread.start()
    event.wait(timeout=timeout_sec)
    server.server_close()
    thread.join(timeout=1.0)
    return _OAuthCallbackHandler.redirect_url


def _build_openai_codex_headers(*, content_type: str, accept: str) -> dict[str, str]:
    return {
        "Content-Type": content_type,
        "Accept": accept,
        "originator": OPENAI_CODEX_ORIGINATOR,
        "User-Agent": OPENAI_CODEX_ORIGINATOR,
    }
