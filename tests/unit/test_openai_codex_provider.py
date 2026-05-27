from __future__ import annotations

import asyncio
import json
from http.client import IncompleteRead
from pathlib import Path

import pytest

from copenet.core.provider_auth.store import ProviderAuthProfile, ProviderAuthStore
from copenet.providers.openai_codex import OpenAICodexProvider


class FakeOpenAICodexSseResponse:
    def __init__(self, lines: list[bytes], read_exception: Exception | None = None) -> None:
        self.headers = {"Content-Type": "text/event-stream"}
        self.status = 200
        self._lines = lines
        self._read_exception = read_exception

    def __enter__(self) -> "FakeOpenAICodexSseResponse":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None

    def __iter__(self):
        yield from self._lines
        if self._read_exception is not None:
            raise self._read_exception

    def read(self) -> bytes:
        if self._read_exception is not None:
            raise self._read_exception
        return b"".join(self._lines)


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

    assert [model.id for model in models] == ["gpt-5.5", "gpt-5.4"]
    assert models[0].capabilities["toolCalls"] is False
    assert models[0].capabilities["promptedToolUse"] is True


@pytest.mark.asyncio
async def test_openai_codex_run_posts_prompt_and_system_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = OpenAICodexProvider(auth_service=StubAuthService())
    captured: dict[str, object] = {}
    lines = [
        b'data: {"type":"response.output_text.delta","delta":"hello from codex"}\n\n',
        b'data: {"type":"response.completed","response":{"id":"resp_123","output":[]}}\n\n',
    ]

    def fake_urlopen(req, timeout: float) -> FakeOpenAICodexSseResponse:
        captured.update({
            "url": req.full_url,
            "payload": json.loads(req.data.decode("utf-8")),
            "authorization": req.headers.get("Authorization"),
            "account_id": req.headers.get("Chatgpt-account-id"),
        })
        return FakeOpenAICodexSseResponse(lines)

    monkeypatch.setattr("copenet.providers.openai_codex.request.urlopen", fake_urlopen)

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
    assert captured["authorization"] == "Bearer access-token"
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
async def test_openai_codex_run_streams_sse_deltas(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = OpenAICodexProvider(auth_service=StubAuthService())
    lines = [
        b'data: {"type":"response.output_text.delta","delta":"hello "}\n\n',
        b'data: {"type":"response.output_text.delta","delta":"world"}\n\n',
        b'data: {"type":"response.completed","response":{"id":"resp_123","output":[]}}\n\n',
        b"data: [DONE]\n\n",
    ]

    monkeypatch.setattr(
        "copenet.providers.openai_codex.request.urlopen",
        lambda req, timeout: FakeOpenAICodexSseResponse(lines),
    )

    events = []
    async for event in provider.run(
        prompt="Say hello.",
        provider_session_id=None,
        abort_event=asyncio.Event(),
        model="gpt-5.5",
        system_prompt=None,
    ):
        events.append(event)

    assert [event.text for event in events if event.kind == "delta"] == ["hello ", "world"]
    assert events[-1].kind == "final"


@pytest.mark.asyncio
async def test_openai_codex_run_preserves_partial_text_after_incomplete_read(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = OpenAICodexProvider(auth_service=StubAuthService())
    lines = [b'data: {"type":"response.output_text.delta","delta":"partial answer"}\n\n']

    monkeypatch.setattr(
        "copenet.providers.openai_codex.request.urlopen",
        lambda req, timeout: FakeOpenAICodexSseResponse(
            lines,
            read_exception=IncompleteRead(partial=b"".join(lines), expected=1_095_113),
        ),
    )

    events = []
    async for event in provider.run(
        prompt="Say something.",
        provider_session_id=None,
        abort_event=asyncio.Event(),
        model="gpt-5.5",
        system_prompt=None,
    ):
        events.append(event)

    assert [event.text for event in events if event.kind == "delta"] == ["partial answer"]
    assert events[-1].kind == "final"


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
