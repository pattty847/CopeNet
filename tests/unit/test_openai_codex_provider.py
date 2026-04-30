from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from copenet.core.provider_auth.store import ProviderAuthProfile, ProviderAuthStore
from copenet.providers.openai_codex import OpenAICodexProvider


class StubAuthService:
    def __init__(self, authenticated: bool = True) -> None:
        self._authenticated = authenticated
        self._profile = ProviderAuthProfile(
            provider="openai-codex",
            profile_id="openai-codex:default",
            access_token="access-token",
            refresh_token="refresh-token",
            expires_at=2_000_000_000_000,
            account_id="acct_123",
            scopes=("openid", "profile"),
            updated_at="2026-04-29T12:00:00Z",
        )

    def status(self) -> dict[str, object]:
        return {
            "provider": "openai-codex",
            "profileId": "openai-codex:default",
            "requiresAuth": True,
            "authType": "oauth",
            "authenticated": self._authenticated,
            "expired": False,
            "accountId": "acct_123" if self._authenticated else None,
            "expiresAt": self._profile.expires_at if self._authenticated else None,
            "scopes": ["openid", "profile"],
            "storePath": "/tmp/openai-codex.json",
        }

    def ensure_valid_profile(self) -> ProviderAuthProfile:
        if not self._authenticated:
            raise RuntimeError("not authenticated")
        return self._profile


@pytest.mark.asyncio
async def test_openai_codex_describe_reports_auth_status() -> None:
    provider = OpenAICodexProvider(auth_service=StubAuthService(authenticated=False))

    description = await provider.describe()

    assert description["requiresAuth"] is True
    assert description["authenticated"] is False
    assert description["capabilities"]["toolCalls"] is False
    assert description["capabilities"]["promptedToolUse"] is True


@pytest.mark.asyncio
async def test_openai_codex_list_models_exposes_static_catalog() -> None:
    provider = OpenAICodexProvider(auth_service=StubAuthService())

    models = await provider.list_models()

    assert [model.id for model in models] == ["gpt-5.4", "gpt-5.5"]
    assert models[0].capabilities["toolCalls"] is False
    assert models[0].capabilities["promptedToolUse"] is True


@pytest.mark.asyncio
async def test_openai_codex_run_posts_prompt_and_system_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = OpenAICodexProvider(auth_service=StubAuthService())
    captured: dict[str, object] = {}

    def fake_post_responses(*, url: str, payload: dict, access_token: str, account_id: str | None) -> dict:
        captured.update({
            "url": url,
            "payload": payload,
            "access_token": access_token,
            "account_id": account_id,
        })
        return {
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": "hello from codex"}],
                }
            ]
        }

    monkeypatch.setattr("copenet.providers.openai_codex._post_responses", fake_post_responses)

    events = []
    async for event in provider.run(
        prompt="Inspect the repo",
        provider_session_id=None,
        abort_event=asyncio.Event(),
        model="gpt-5.5",
        system_prompt="Use tools carefully.",
    ):
        events.append(event)

    assert captured["url"] == "https://chatgpt.com/backend-api/codex/responses"
    assert captured["access_token"] == "access-token"
    assert captured["account_id"] == "acct_123"
    assert captured["payload"] == {
        "model": "gpt-5.5",
        "input": [{"role": "user", "content": [{"type": "input_text", "text": "Inspect the repo"}]}],
        "store": False,
        "stream": True,
        "text": {"verbosity": "medium"},
        "instructions": "Use tools carefully.",
    }
    assert [event.kind for event in events] == ["delta", "final"]
    assert events[0].text == "hello from codex"


@pytest.mark.asyncio
async def test_openai_codex_run_rejects_unsupported_model() -> None:
    provider = OpenAICodexProvider(auth_service=StubAuthService())

    with pytest.raises(ValueError, match="unsupported openai-codex model"):
        async for _event in provider.run(
            prompt="hello",
            provider_session_id=None,
            abort_event=asyncio.Event(),
            model="gpt-5.1-codex-mini",
            system_prompt=None,
        ):
            pass


def test_openai_codex_payload_includes_default_instructions_when_missing() -> None:
    from copenet.providers.openai_codex import OPENAI_CODEX_DEFAULT_INSTRUCTIONS, _build_payload

    payload = _build_payload(model="gpt-5.4", prompt="Say OK.", system_prompt=None)

    assert payload["instructions"] == OPENAI_CODEX_DEFAULT_INSTRUCTIONS


def test_openai_codex_sse_completed_response_uses_deltas() -> None:
    from copenet.providers.openai_codex import _decode_openai_codex_response_body

    payload = _decode_openai_codex_response_body(
        raw_body=(
            'data: {"type":"response.output_text.delta","delta":"hello "}\n\n'
            'data: {"type":"response.output_text.delta","delta":"world"}\n\n'
            'data: {"type":"response.completed","response":{"id":"resp_123","output":[]}}\n\n'
            "data: [DONE]\n\n"
        ),
        content_type="text/event-stream",
    )

    assert payload["output_text"] == "hello world"


def test_openai_codex_sse_without_content_type_still_parses() -> None:
    from copenet.providers.openai_codex import _decode_openai_codex_response_body

    payload = _decode_openai_codex_response_body(
        raw_body=(
            'event: response.created\n'
            'data: {"type":"response.output_text.delta","delta":"hello"}\n\n'
            'event: response.completed\n'
            'data: {"type":"response.completed","response":{"id":"resp_123","output":[]}}\n\n'
        ),
        content_type="",
    )

    assert payload["output_text"] == "hello"


def test_openai_codex_sse_failure_raises() -> None:
    from copenet.providers.openai_codex import _decode_openai_codex_response_body

    with pytest.raises(RuntimeError, match="bad request"):
        _decode_openai_codex_response_body(
            raw_body='data: {"type":"response.failed","error":{"message":"bad request"}}\n\n',
            content_type="text/event-stream",
        )
