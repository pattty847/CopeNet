from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from copenet.core.provider_auth.openai_codex import OPENAI_CODEX_PROVIDER_ID, OpenAICodexAuthService
from copenet.core.provider_auth.store import ProviderAuthProfile, ProviderAuthStore



def _jwt(payload: dict) -> str:
    header = base64.urlsafe_b64encode(json.dumps({"alg": "none", "typ": "JWT"}).encode()).rstrip(b"=").decode()
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
    return f"{header}.{body}.sig"



def _store(tmp_path: Path) -> ProviderAuthStore:
    return ProviderAuthStore(tmp_path / "openai-codex.json")



def test_provider_auth_store_round_trip(tmp_path: Path) -> None:
    store = _store(tmp_path)
    profile = ProviderAuthProfile(
        provider=OPENAI_CODEX_PROVIDER_ID,
        profile_id="openai-codex:default",
        access_token="access",
        refresh_token="refresh",
        expires_at=2_000_000_000_000,
        account_id="acct_123",
        scopes=("openid", "profile"),
        updated_at="2026-04-29T12:00:00Z",
    )

    store.save(profile)
    loaded = store.load()

    assert loaded == profile



def test_openai_codex_begin_login_returns_authorize_url(tmp_path: Path) -> None:
    service = OpenAICodexAuthService(store=_store(tmp_path))

    result = service.begin_login()

    assert result["provider"] == OPENAI_CODEX_PROVIDER_ID
    assert result["loginToken"]
    assert result["redirectUri"] == "http://localhost:1455/auth/callback"
    assert "auth.openai.com/oauth/authorize" in str(result["authorizeUrl"])
    assert "code_challenge=" in str(result["authorizeUrl"])



def test_openai_codex_complete_login_saves_profile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    service = OpenAICodexAuthService(store=_store(tmp_path))
    begun = service.begin_login()
    access_token = _jwt(
        {
            "exp": 2_000_000_000,
            "https://api.openai.com/auth": {"chatgpt_account_id": "acct_123"},
        }
    )

    monkeypatch.setattr(
        "copenet.core.provider_auth.openai_codex._token_request",
        lambda payload: {
            "access_token": access_token,
            "refresh_token": "refresh-token",
            "expires_in": 3600,
            "scope": "openid profile email offline_access",
        },
    )

    result = service.complete_login(
        login_token=str(begun["loginToken"]),
        redirect_url=f"http://localhost:1455/auth/callback?code=test-code&state={begun['state']}",
    )

    stored = service.store.load()
    assert result["authenticated"] is True
    assert stored is not None
    assert stored.account_id == "acct_123"
    assert stored.refresh_token == "refresh-token"
    assert stored.scopes == ("openid", "profile", "email", "offline_access")



def test_openai_codex_ensure_valid_profile_refreshes_expired_token(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = _store(tmp_path)
    expired = ProviderAuthProfile(
        provider=OPENAI_CODEX_PROVIDER_ID,
        profile_id="openai-codex:default",
        access_token=_jwt({"exp": 1, "https://api.openai.com/auth": {"chatgpt_account_id": "acct_old"}}),
        refresh_token="old-refresh",
        expires_at=1,
        account_id="acct_old",
        scopes=("openid",),
        updated_at="2026-04-29T12:00:00Z",
    )
    store.save(expired)
    service = OpenAICodexAuthService(store=store)
    refreshed_token = _jwt(
        {
            "exp": 2_000_000_100,
            "https://api.openai.com/auth": {"chatgpt_account_id": "acct_new"},
        }
    )

    monkeypatch.setattr(
        "copenet.core.provider_auth.openai_codex._token_request",
        lambda payload: {
            "access_token": refreshed_token,
            "refresh_token": "new-refresh",
            "expires_in": 7200,
            "scope": "openid profile",
        },
    )

    profile = service.ensure_valid_profile()

    assert profile.refresh_token == "new-refresh"
    assert profile.account_id == "acct_new"
    assert store.load() == profile
