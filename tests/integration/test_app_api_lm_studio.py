from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from copenet.core.orchestrator import Orchestrator
from copenet.core.sessions import SessionStore, TranscriptStore
from copenet.host.api import create_app
from copenet.providers.local_http import LmStudioProvider


class _LmStudioFixture:
    def __init__(self) -> None:
        self.models = [
            {
                "type": "llm",
                "publisher": "openai",
                "key": "openai/gpt-oss-20b",
                "display_name": "GPT OSS 20B",
                "architecture": "gpt-oss",
                "loaded_instances": [],
                "max_context_length": 131072,
                "format": "gguf",
                "capabilities": {"vision": False, "trained_for_tool_use": True},
                "description": None,
            }
        ]
        self.load_calls: list[dict] = []
        self.chat_calls: list[dict] = []


@pytest.fixture
def lmstudio_server():
    state = _LmStudioFixture()

    class Handler(BaseHTTPRequestHandler):
        def _json(self, status: int, payload: dict) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/api/v1/models":
                return self._json(200, {"models": state.models})
            self.send_error(404)

        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
            if self.path == "/api/v1/models/load":
                state.load_calls.append(payload)
                instance_id = f"{payload['model']}#instance-1"
                state.models[0]["loaded_instances"] = [{"id": instance_id, "config": {"context_length": 4096}}]
                return self._json(200, {"type": "llm", "instance_id": instance_id, "status": "loaded"})
            if self.path == "/v1/chat/completions":
                state.chat_calls.append(payload)
                body = (
                    'data: {"choices":[{"delta":{"content":"hello from lm studio"}}]}\n\n'
                    'data: [DONE]\n\n'
                ).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            self.send_error(404)

        def log_message(self, format: str, *args) -> None:  # noqa: A003
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield state, f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join()


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def app_client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, lmstudio_server):
    _, base_url = lmstudio_server
    monkeypatch.setenv("COPNET_WORKDIR", str(tmp_path))
    orchestrator = Orchestrator(
        session_store=SessionStore(path=tmp_path / "index.json"),
        transcript_store=TranscriptStore(root_dir=tmp_path / "transcripts"),
        sessions_dir=tmp_path,
        providers={"lm-studio": LmStudioProvider(base_url=base_url)},
    )
    _, token = orchestrator.register_app(app_id="subtext", display_name="Subtext", default_provider="lm-studio")
    app = create_app(orchestrator)
    with TestClient(app) as client:
        yield client, orchestrator, token


def test_app_api_lists_lm_studio_models_with_native_metadata(app_client) -> None:
    client, _, token = app_client

    response = client.get("/api/v1/models", headers=_auth(token), params={"provider": "lm-studio"})

    assert response.status_code == 200
    models = response.json()["models"]
    assert [model["id"] for model in models] == ["openai/gpt-oss-20b"]
    assert models[0]["metadata"]["loadedInstanceCount"] == 0


def test_app_api_lm_studio_session_cold_loads_and_uses_instance_id_for_chat(app_client, lmstudio_server) -> None:
    client, orchestrator, token = app_client
    state, _ = lmstudio_server

    created = client.post(
        "/api/v1/sessions",
        headers=_auth(token),
        json={"id": "lm-chat", "provider": "lm-studio", "model": "openai/gpt-oss-20b"},
    )
    assert created.status_code == 201

    sent = client.post(
        "/api/v1/sessions/lm-chat/messages",
        headers=_auth(token),
        json={"content": "Say hi", "provider": "lm-studio", "model": "openai/gpt-oss-20b"},
    )

    assert sent.status_code == 200
    payload = sent.json()
    assert payload["event"]["state"] == "final"
    assert payload["event"]["message"]["content"] == "hello from lm studio"
    assert state.load_calls == [{"model": "openai/gpt-oss-20b"}]
    assert state.chat_calls[0]["model"] == "openai/gpt-oss-20b#instance-1"

    mapping = orchestrator._app_store.get_mapping("subtext", "lm-chat")
    assert mapping is not None
    internal = orchestrator.resolve_session(mapping.internal_session_key)
    assert internal is not None
    assert internal["provider"] == "lm-studio"
    assert internal["model"] == "openai/gpt-oss-20b"
