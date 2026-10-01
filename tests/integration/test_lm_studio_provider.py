"""LM Studio lane: real HTTP against a loopback stand-in for LM Studio's server.

The provider speaks LM Studio's Responses endpoint, so the tests drive it through
the same harness loop openai-codex uses and assert on the request bodies LM Studio
would actually receive.
"""

from __future__ import annotations

import asyncio
import json
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

from copenet.core.harness.capabilities import ModelCapabilityProfile
from copenet.core.harness.planning import HarnessTurnPlan
from copenet.core.harness.tool_loop import run_with_responses_tools
from copenet.core.tools import (
    ToolDescriptor,
    ToolExecutionContext,
    ToolExecutionRequest,
    ToolExecutionResult,
    ToolPolicy,
    build_responses_tool_schemas,
)
from copenet.providers import RESOLVED_MODEL_META_KEY, TOKEN_USAGE_META_KEY, LmStudioProvider

MODEL = "omnicoder-9b"

MODELS_PAYLOAD = {
    "models": [
        {
            "type": "llm",
            "key": MODEL,
            "display_name": "OmniCoder 9B",
            "max_context_length": 262144,
            "loaded_instances": [{"id": MODEL, "config": {"context_length": 32768}}],
            "capabilities": {"vision": False, "trained_for_tool_use": True},
        },
        {"type": "llm", "key": "qwen3-4b", "max_context_length": 40960, "loaded_instances": []},
        {"type": "embedding", "key": "nomic-embed-text", "max_context_length": 2048, "loaded_instances": []},
    ]
}


def _sse(events: list[dict[str, Any]]) -> bytes:
    return b"".join(f"data: {json.dumps(event)}\n\n".encode() for event in events)


def _tool_call_turn() -> bytes:
    call = {"type": "function_call", "id": "fc_1", "call_id": "call_1", "name": "files_read", "arguments": ""}
    done = {**call, "arguments": json.dumps({"path": "foo.txt", "activity_title": "Reading foo"})}
    return _sse([
        {"type": "response.created", "response": {"model": MODEL}},
        {"type": "response.output_item.added", "item": call},
        {"type": "response.function_call_arguments.delta", "item_id": "fc_1", "delta": done["arguments"]},
        {"type": "response.output_item.done", "item": done},
        {
            "type": "response.completed",
            "response": {"status": "completed", "output": [done], "usage": {"input_tokens": 900, "output_tokens": 40}},
        },
    ])


def _answer_turn() -> bytes:
    message = {
        "type": "message",
        "id": "msg_1",
        "role": "assistant",
        "content": [{"type": "output_text", "text": "foo.txt says hello"}],
    }
    return _sse([
        {"type": "response.created", "response": {"model": MODEL}},
        {"type": "response.output_text.delta", "item_id": "msg_1", "delta": "foo.txt says hello"},
        {"type": "response.output_item.done", "item": message},
        {
            "type": "response.completed",
            "response": {"status": "completed", "output": [message], "usage": {"input_tokens": 980, "output_tokens": 6}},
        },
    ])


class FakeLmStudio:
    """Serves /api/v1/models and scripted /v1/responses turns; records request bodies."""

    def __init__(self, turns: list[bytes], status: int = 200) -> None:
        self.turns = list(turns)
        self.status = status
        self.requests: list[dict[str, Any]] = []
        server = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args: object) -> None:
                return None

            def do_GET(self) -> None:
                body = json.dumps(MODELS_PAYLOAD).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self) -> None:
                length = int(self.headers["Content-Length"])
                server.requests.append(json.loads(self.rfile.read(length)))
                if server.status != 200:
                    body = b'{"error":"Model does not support tools"}'
                    self.send_response(server.status)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                body = server.turns.pop(0)
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.base_url = f"http://127.0.0.1:{self._httpd.server_address[1]}"
        threading.Thread(target=self._httpd.serve_forever, daemon=True).start()

    def close(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()


@pytest.fixture
def fake_server():
    servers: list[FakeLmStudio] = []

    def start(turns: list[bytes], status: int = 200) -> FakeLmStudio:
        servers.append(FakeLmStudio(turns, status))
        return servers[-1]

    yield start
    for server in servers:
        server.close()


def _plan() -> HarnessTurnPlan:
    tool = ToolDescriptor(
        id="files.read",
        name="Read File",
        description="Read a file.",
        category="repo-read",
        input_schema={"type": "object", "properties": {"path": {"type": "string"}}},
        capabilities=["filesystem", "read"],
        evidence_role="grounding",
        side_effect="read",
    )
    return HarnessTurnPlan(
        provider="lm-studio",
        model=MODEL,
        capability_profile=ModelCapabilityProfile(provider="lm-studio", model=MODEL, responses_api=True),
        tools=[tool],
        will_attempt_tool_loop=True,
        tool_execution_mode="responses",
    )


def _context(tmp_path: Path) -> ToolExecutionContext:
    return ToolExecutionContext(
        workdir=tmp_path,
        session_workspace_root=tmp_path,
        session_key="s1",
        provider_name="lm-studio",
        model=MODEL,
        session_store=None,  # type: ignore[arg-type]
        transcript_store=None,  # type: ignore[arg-type]
        providers={},
        policy=ToolPolicy(),
        available_tools=[],
        memory_service=None,
        workspace_intel_service=None,
        artifact_store=None,
        task_prompt_id=None,
        run_id="run1",
        trace=None,
    )


@pytest.mark.asyncio
async def test_lm_studio_budget_reads_the_loaded_context_not_the_architecture_maximum(fake_server) -> None:
    provider = LmStudioProvider(base_url=fake_server([]).base_url)

    models = await provider.list_models()

    assert [model.id for model in models] == [MODEL, "qwen3-4b"]
    loaded, unloaded = models
    assert loaded.metadata["maxContextLength"] == 32768
    assert loaded.metadata["architectureMaxContextLength"] == 262144
    assert unloaded.metadata["maxContextLength"] == 40960
    meta = await provider.describe()
    assert meta["available"] is True
    assert meta["defaultModel"] == MODEL
    assert meta["loadedModels"] == [{"id": MODEL, "contextLength": 32768}]
    assert meta["capabilities"]["responsesApi"] is True


@pytest.mark.asyncio
async def test_lm_studio_unreachable_server_reports_unavailable_quickly() -> None:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    provider = LmStudioProvider(base_url=f"http://127.0.0.1:{port}")

    started = time.monotonic()
    meta = await provider.describe()

    assert time.monotonic() - started < 3
    assert meta["available"] is False
    assert f"127.0.0.1:{port}" in meta["error"]
    assert "COPNET_LM_STUDIO_BASE_URL" in meta["error"]


@pytest.mark.asyncio
async def test_lm_studio_runs_a_tool_call_round_trip_on_the_responses_loop(fake_server, tmp_path: Path) -> None:
    server = fake_server([_tool_call_turn(), _answer_turn()])
    provider = LmStudioProvider(base_url=server.base_url)
    executed: list[ToolExecutionRequest] = []

    async def tool_executor(request: ToolExecutionRequest, context: ToolExecutionContext) -> ToolExecutionResult:
        executed.append(request)
        return ToolExecutionResult(tool_id="files.read", ok=True, summary="Read foo.txt", body="hello")

    plan = _plan()
    events = [
        event
        async for event in run_with_responses_tools(
            provider=provider,
            messages=[{"role": "user", "content": [{"type": "input_text", "text": "what is in foo.txt?"}]}],
            abort_event=asyncio.Event(),
            model=MODEL,
            instructions="be useful",
            plan=plan,
            tool_executor=tool_executor,
            tool_context=_context(tmp_path),
            session_id="s1",
            reasoning={"effort": "medium"},
        )
    ]

    # The model's safe name maps back to the dotted tool id, and the activity title rides along.
    assert [(request.tool_id, request.arguments, request.activity_title) for request in executed] == [
        ("files.read", {"path": "foo.txt"}, "Reading foo")
    ]
    first, second = server.requests
    assert first["model"] == MODEL
    assert first["instructions"] == "be useful"
    assert first["tools"] == build_responses_tool_schemas(plan.tools)
    assert first["tool_choice"] == "auto"
    # Codex-only fields are not guessed onto a local model.
    for key in ("reasoning", "prompt_cache_key", "include", "store"):
        assert key not in first
    # The follow-up replays the call (sanitized name) and its output, paired by call_id.
    replayed = {item.get("type"): item for item in second["input"] if item.get("type")}
    assert replayed["function_call"]["name"] == "files_read"
    assert replayed["function_call"]["call_id"] == "call_1"
    assert replayed["function_call_output"]["call_id"] == "call_1"
    assert "hello" in replayed["function_call_output"]["output"]

    metas = [event.metadata for event in events if event.kind == "meta" and event.metadata]
    assert {meta[RESOLVED_MODEL_META_KEY] for meta in metas if RESOLVED_MODEL_META_KEY in meta} == {MODEL}
    assert [meta[TOKEN_USAGE_META_KEY]["inputTokens"] for meta in metas if TOKEN_USAGE_META_KEY in meta] == [900, 980]
    assert "".join(event.text or "" for event in events if event.kind == "delta") == "foo.txt says hello"
    assert events[-1].kind == "final"


@pytest.mark.asyncio
async def test_lm_studio_http_error_names_the_lane_and_carries_the_server_detail(fake_server) -> None:
    provider = LmStudioProvider(base_url=fake_server([], status=400).base_url)

    with pytest.raises(RuntimeError, match=r"lm-studio request failed \(400\).*does not support tools"):
        async for _ in provider.stream_responses(
            messages=[],
            tools=None,
            model=MODEL,
            instructions=None,
            abort_event=asyncio.Event(),
        ):
            pass


@pytest.mark.asyncio
async def test_lm_studio_plain_turn_streams_text_without_tools(fake_server) -> None:
    server = fake_server([_answer_turn()])
    provider = LmStudioProvider(base_url=server.base_url)

    events = [event async for event in provider.run("hi", None, asyncio.Event(), model=None, system_prompt="sys")]

    # No model chosen: the loaded one is used rather than the first downloaded.
    assert server.requests[0]["model"] == MODEL
    assert "tools" not in server.requests[0]
    assert "".join(event.text or "" for event in events if event.kind == "delta") == "foo.txt says hello"
    assert not any((event.metadata or {}).get("responsesCompleted") for event in events)
    assert events[-1].kind == "final"


@pytest.mark.asyncio
async def test_lm_studio_address_comes_from_the_environment(fake_server, monkeypatch) -> None:
    server = fake_server([])
    monkeypatch.setenv("COPNET_LM_STUDIO_BASE_URL", server.base_url + "/")

    meta = await LmStudioProvider().describe()

    assert meta["baseUrl"] == server.base_url
    assert meta["available"] is True
