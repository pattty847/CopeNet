from __future__ import annotations

import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib import error

import pytest

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
            },
            {
                "type": "embedding",
                "publisher": "nomic-ai",
                "key": "nomic-embed-text-v1.5",
                "display_name": "Nomic Embed Text v1.5",
                "loaded_instances": [],
                "max_context_length": 2048,
                "format": "gguf",
            },
        ]
        self.load_calls: list[dict] = []
        self.unload_calls: list[dict] = []
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
                model_key = payload["model"]
                instance_id = model_key if model_key == "already-loaded" else f"{model_key}#instance-1"
                for row in state.models:
                    if row.get("key") == model_key:
                        row["loaded_instances"] = [{"id": instance_id, "config": {"context_length": 4096}}]
                        break
                return self._json(200, {"type": "llm", "instance_id": instance_id, "status": "loaded", "load_time_seconds": 0.1})
            if self.path == "/api/v1/models/unload":
                state.unload_calls.append(payload)
                target = payload["instance_id"]
                for row in state.models:
                    row["loaded_instances"] = [inst for inst in row.get("loaded_instances", []) if inst.get("id") != target]
                return self._json(200, {"instance_id": target})
            if self.path == "/v1/chat/completions":
                state.chat_calls.append(payload)
                if payload.get("stream") is False:
                    if payload.get("tools"):
                        return self._json(
                            200,
                            {
                                "choices": [
                                    {
                                        "finish_reason": "tool_calls",
                                        "message": {
                                            "role": "assistant",
                                            "content": "",
                                            "tool_calls": [
                                                {
                                                    "id": "call-1",
                                                    "type": "function",
                                                    "function": {
                                                        "name": "files.read",
                                                        "arguments": json.dumps({"path": "README.md"}),
                                                    },
                                                }
                                            ],
                                        },
                                    }
                                ]
                            },
                        )
                    return self._json(
                        200,
                        {
                            "choices": [
                                {
                                    "finish_reason": "stop",
                                    "message": {
                                        "role": "assistant",
                                        "content": "plain final answer",
                                    },
                                }
                            ]
                        },
                    )
                body = (
                    'data: {"choices":[{"delta":{"content":"hello"}}]}\n\n'
                    'data: {"choices":[{"delta":{"content":" world"}}]}\n\n'
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


@pytest.mark.asyncio
async def test_list_models_uses_native_catalog_and_surfaces_loaded_instances(lmstudio_server) -> None:
    state, base_url = lmstudio_server
    state.models[0]["loaded_instances"] = [{"id": "openai/gpt-oss-20b", "config": {"context_length": 8192}}]
    provider = LmStudioProvider(base_url=base_url)

    models = await provider.list_models()
    loaded = await provider.list_loaded_instances()

    assert [model.id for model in models] == ["openai/gpt-oss-20b", "nomic-embed-text-v1.5"]
    assert models[0].capabilities["toolCalls"] is True
    assert models[0].metadata["loadedInstanceCount"] == 1
    assert models[0].metadata["loadedInstances"][0]["instanceId"] == "openai/gpt-oss-20b"
    assert loaded == [
        {
            "instanceId": "openai/gpt-oss-20b",
            "modelKey": "openai/gpt-oss-20b",
            "type": "llm",
            "config": {"context_length": 8192},
        }
    ]


@pytest.mark.asyncio
async def test_ensure_model_loaded_reuses_loaded_instance_or_loads_on_demand(lmstudio_server) -> None:
    state, base_url = lmstudio_server
    provider = LmStudioProvider(base_url=base_url)

    state.models[0]["loaded_instances"] = [{"id": "already-loaded", "config": {"context_length": 4096}}]
    reused = await provider.ensure_model_loaded("already-loaded")
    loaded_by_key = await provider.ensure_model_loaded("openai/gpt-oss-20b")
    state.models[0]["loaded_instances"] = []
    cold_loaded = await provider.ensure_model_loaded("openai/gpt-oss-20b")

    assert reused == "already-loaded"
    assert loaded_by_key == "already-loaded"
    assert cold_loaded == "openai/gpt-oss-20b#instance-1"
    assert state.load_calls == [{"model": "openai/gpt-oss-20b"}]


@pytest.mark.asyncio
async def test_ensure_model_loaded_defaults_to_existing_loaded_chat_instance(lmstudio_server) -> None:
    state, base_url = lmstudio_server
    provider = LmStudioProvider(base_url=base_url)

    state.models[0]["loaded_instances"] = [{"id": "openai/gpt-oss-20b#loaded", "config": {"context_length": 4096}}]

    instance_id = await provider.ensure_model_loaded(None)

    assert instance_id == "openai/gpt-oss-20b#loaded"
    assert state.load_calls == []


@pytest.mark.asyncio
async def test_ensure_model_loaded_switches_to_requested_model_even_if_another_chat_model_is_loaded(lmstudio_server) -> None:
    state, base_url = lmstudio_server
    provider = LmStudioProvider(base_url=base_url)

    state.models[0]["loaded_instances"] = [{"id": "openai/gpt-oss-20b#loaded", "config": {"context_length": 4096}}]
    state.models.append(
        {
            "type": "llm",
            "publisher": "google",
            "key": "google/gemma-4-e2b",
            "display_name": "Gemma 4 E2B",
            "architecture": "gemma",
            "loaded_instances": [],
            "max_context_length": 32768,
            "format": "gguf",
            "capabilities": {"vision": False, "trained_for_tool_use": False},
            "description": None,
        }
    )

    instance_id = await provider.ensure_model_loaded("google/gemma-4-e2b")

    assert instance_id == "google/gemma-4-e2b#instance-1"
    assert state.load_calls == [{"model": "google/gemma-4-e2b"}]


@pytest.mark.asyncio
async def test_run_cold_loads_model_before_chat(lmstudio_server) -> None:
    state, base_url = lmstudio_server
    provider = LmStudioProvider(base_url=base_url)

    events = [
        event
        async for event in provider.run(
            prompt="Say hi",
            provider_session_id="session-1",
            abort_event=asyncio.Event(),
            model="openai/gpt-oss-20b",
            system_prompt="You are terse.",
        )
    ]

    assert [event.kind for event in events] == ["delta", "delta", "final"]
    assert "".join(event.text or "" for event in events) == "hello world"
    assert state.load_calls == [{"model": "openai/gpt-oss-20b"}]
    assert state.chat_calls[0]["model"] == "openai/gpt-oss-20b#instance-1"
    assert state.chat_calls[0]["messages"] == [
        {"role": "system", "content": "You are terse."},
        {"role": "user", "content": "Say hi"},
    ]


@pytest.mark.asyncio
async def test_chat_completion_sends_tools_when_requested(lmstudio_server) -> None:
    state, base_url = lmstudio_server
    provider = LmStudioProvider(base_url=base_url)

    response = await provider.chat_completion(
        messages=[{"role": "user", "content": "Inspect README.md"}],
        model="openai/gpt-oss-20b",
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "files.read",
                    "description": "Read a file.",
                    "parameters": {
                        "type": "object",
                        "properties": {"path": {"type": "string"}},
                        "required": ["path"],
                    },
                },
            }
        ],
    )

    assert state.chat_calls[-1]["stream"] is False
    assert state.chat_calls[-1]["tools"][0]["function"]["name"] == "files.read"
    assert response["choices"][0]["message"]["tool_calls"][0]["function"]["name"] == "files.read"


@pytest.mark.asyncio
async def test_chat_completion_surfaces_timeout_context(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = LmStudioProvider(base_url="http://127.0.0.1:1234")

    async def fake_ensure_model_loaded(explicit_model: str | None) -> str:
        assert explicit_model == "google/gemma-4-e4b"
        return "google/gemma-4-e4b#instance-1"

    def fake_request(*args, **kwargs):
        raise error.URLError("timed out")

    monkeypatch.setattr(provider, "ensure_model_loaded", fake_ensure_model_loaded)
    monkeypatch.setattr("copenet.providers.local_http._http_json_request", fake_request)

    with pytest.raises(RuntimeError, match="LM Studio chat completion timed out or failed: timed out"):
        await provider.chat_completion(
            messages=[{"role": "user", "content": "Summarize the repo"}],
            model="google/gemma-4-e4b",
            tools=None,
        )


@pytest.mark.asyncio
async def test_unload_model_posts_instance_id(lmstudio_server) -> None:
    state, base_url = lmstudio_server
    provider = LmStudioProvider(base_url=base_url)

    await provider.unload_model("openai/gpt-oss-20b#instance-1")

    assert state.unload_calls == [{"instance_id": "openai/gpt-oss-20b#instance-1"}]


@pytest.mark.asyncio
async def test_describe_includes_native_model_lifecycle_capability(lmstudio_server) -> None:
    _, base_url = lmstudio_server
    provider = LmStudioProvider(base_url=base_url)

    meta = await provider.describe()

    assert meta["id"] == "lm-studio"
    assert meta["available"] is True
    assert meta["capabilities"]["nativeModelLifecycle"] is True
    assert meta["capabilities"]["toolCalls"] is True
