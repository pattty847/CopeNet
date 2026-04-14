from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from copenet.core.orchestrator import Orchestrator
from copenet.core.sessions import SessionStore, TranscriptStore
from copenet.host.api import create_app
from copenet.providers import ProviderEvent, ProviderModel


class FakeProvider:
    def __init__(self, *, name: str = "fake", response_text: str = "hello from fake provider", wait_for_abort: bool = False) -> None:
        self.name = name
        self.display_name = name.title()
        self.response_text = response_text
        self.wait_for_abort = wait_for_abort

    async def run(self, prompt: str, provider_session_id: str | None, abort_event: asyncio.Event, model: str | None = None, system_prompt: str | None = None):
        if self.wait_for_abort:
            await abort_event.wait()
            return
        yield ProviderEvent(kind="delta", text=self.response_text, provider_session_id=provider_session_id or f"{self.name}-session")
        yield ProviderEvent(kind="final")

    async def describe(self) -> dict:
        return {
            "id": self.name,
            "displayName": self.display_name,
            "available": True,
            "capabilities": {"chat": True, "streaming": True, "toolCalls": False},
        }

    async def list_models(self) -> list[ProviderModel]:
        return [ProviderModel(id="model-a", display_name="Model A", provider=self.name, capabilities={"chat": True})]


class PromptedToolProvider:
    def __init__(self) -> None:
        self.name = "prompted"
        self.display_name = "Prompted"

    async def run(self, prompt: str, provider_session_id: str | None, abort_event: asyncio.Event, model: str | None = None, system_prompt: str | None = None):
        yield ProviderEvent(kind="delta", text='{"tool_id":"files.read","arguments":{"path":"README.md"}}', provider_session_id=provider_session_id or "prompted-session")
        yield ProviderEvent(kind="final")

    async def describe(self) -> dict:
        return {
            "id": self.name,
            "displayName": self.display_name,
            "available": True,
            "capabilities": {"chat": True, "streaming": True, "toolCalls": False, "promptedToolUse": True},
        }

    async def list_models(self) -> list[ProviderModel]:
        return [ProviderModel(id="tool-model", display_name="Tool Model", provider=self.name, capabilities={"chat": True})]


@pytest.fixture
def app_client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("COPNET_WORKDIR", str(tmp_path))
    (tmp_path / "README.md").write_text("# Temp Repo\nhello\n", encoding="utf-8")
    orchestrator = Orchestrator(
        session_store=SessionStore(path=tmp_path / "index.json"),
        transcript_store=TranscriptStore(root_dir=tmp_path / "transcripts"),
        sessions_dir=tmp_path,
        providers={
            "fake": FakeProvider(),
            "blocking": FakeProvider(name="blocking", wait_for_abort=True),
            "prompted": PromptedToolProvider(),
        },
    )
    app_meta, token = orchestrator.register_app(app_id="subtext", display_name="Subtext", default_provider="fake")
    app = create_app(orchestrator)
    with TestClient(app) as client:
        yield client, orchestrator, token, app_meta


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_app_api_auth_and_hashed_token_storage(app_client) -> None:
    client, orchestrator, token, _ = app_client

    unauthorized = client.get("/api/v1/sessions")
    assert unauthorized.status_code == 401

    ok = client.get("/api/v1/providers", headers=_auth(token))
    assert ok.status_code == 200
    assert {row["id"] for row in ok.json()["providers"]} >= {"fake", "blocking", "prompted"}

    stored = json.loads(orchestrator._app_store.path.read_text(encoding="utf-8"))
    assert stored["apps"][0]["app_id"] == "subtext"
    assert stored["apps"][0]["token_hash"] != token
    assert len(stored["apps"][0]["token_hash"]) == 64


def test_app_session_mapping_send_history_and_visibility(app_client) -> None:
    client, orchestrator, token, _ = app_client

    created = client.post(
        "/api/v1/sessions",
        headers=_auth(token),
        json={"id": "chat-1", "title": "Subtext Chat", "provider": "fake", "model": "model-a"},
    )
    assert created.status_code == 201
    session = created.json()["session"]
    assert session["id"] == "chat-1"
    assert session["provider"] == "fake"
    assert session["model"] == "model-a"

    mapping = orchestrator._app_store.get_mapping("subtext", "chat-1")
    assert mapping is not None
    assert mapping.internal_session_key != "chat-1"
    internal = orchestrator.resolve_session(mapping.internal_session_key)
    assert internal is not None
    assert internal["key"].startswith("app-subtext-")

    listing = client.get("/api/v1/sessions", headers=_auth(token))
    assert listing.json()["sessions"] == [session]

    sent = client.post(
        "/api/v1/sessions/chat-1/messages",
        headers=_auth(token),
        json={"content": "Hello from Subtext", "provider": "fake", "model": "model-a"},
    )
    assert sent.status_code == 200
    payload = sent.json()
    assert payload["run"]["status"] == "ok"
    assert payload["event"]["state"] == "final"
    assert payload["event"]["message"]["content"] == "hello from fake provider"

    history = client.get("/api/v1/sessions/chat-1/messages", headers=_auth(token))
    messages = history.json()["messages"]
    assert [message["role"] for message in messages] == ["user", "assistant"]
    assert messages[-1]["content"] == "hello from fake provider"


def test_app_api_safe_default_disables_prompted_tool_loop(app_client) -> None:
    client, _, token, _ = app_client
    created = client.post(
        "/api/v1/sessions",
        headers=_auth(token),
        json={"id": "tool-chat", "provider": "prompted", "model": "tool-model"},
    )
    assert created.status_code == 201

    sent = client.post(
        "/api/v1/sessions/tool-chat/messages",
        headers=_auth(token),
        json={"content": "Read the README", "provider": "prompted", "model": "tool-model"},
    )
    payload = sent.json()
    assert payload["event"]["toolExecution"] is None
    assert payload["event"]["message"]["content"].startswith('{"tool_id":"files.read"')


def test_app_api_sse_stream(app_client) -> None:
    client, _, token, _ = app_client
    created = client.post(
        "/api/v1/sessions",
        headers=_auth(token),
        json={"id": "stream-chat", "provider": "fake", "model": "model-a"},
    )
    assert created.status_code == 201

    with client.stream(
        "GET",
        "/api/v1/sessions/stream-chat/messages/stream",
        headers=_auth(token),
        params={"content": "Stream please", "provider": "fake", "model": "model-a", "idempotency_key": "run-stream-1"},
    ) as response:
        assert response.status_code == 200
        text = "".join(response.iter_text())
    assert "event: chat" in text
    assert '"state": "delta"' in text
    assert '"state": "final"' in text
    assert "event: done" in text

    cancel = client.post("/api/v1/runs/missing-run/cancel", headers=_auth(token))
    assert cancel.status_code == 200
    assert cancel.json() == {"ok": True, "aborted": False, "runIds": []}
