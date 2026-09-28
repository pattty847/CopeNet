"""Sentinel Agent API tool contract, exercised over a local fake HTTP server."""

from __future__ import annotations

import asyncio
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import socket
from threading import Thread
from urllib.parse import parse_qs, urlsplit

import pytest

from copenet.core.sessions.session_store import SessionStore
from copenet.core.sessions.transcript_store import TranscriptStore
from copenet.core.orchestrator.approval_execution import make_approval_gated_executor
from copenet.core.tools import ToolExecutionRequest, ToolRegistry, policy_for_task_mode
from copenet.core.tools.barricade import approval_key
from copenet.core.tools.contracts import ToolExecutionContext
from copenet.core.tools.handlers.sentinel_client import SentinelApiError, sentinel_base_url


META = {"sessionId": "gui-1", "symbol": "BTC-USD", "selectionEpoch": "3",
        "observedAtMs": 1790596800000, "source": "gui-cache", "stale": True,
        "coverage": "partial", "truncated": True}


def envelope(data: dict) -> dict:
    return {"ok": True, "meta": META, "data": data}


@pytest.fixture
def server(monkeypatch: pytest.MonkeyPatch):
    requests: list[tuple[str, str, dict, dict | None]] = []
    behavior = {"operation_status": "rendered", "error": None}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def respond(self):
            parsed = urlsplit(self.path)
            params = parse_qs(parsed.query)
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"]))) if self.command == "POST" else None
            requests.append((self.command, parsed.path, params, body))
            assert self.headers["Host"].startswith("127.0.0.1:")
            if behavior["error"]:
                status, code = behavior["error"]
                response = {"ok": False, "error": {"code": code, "message": "Sentinel rejected request"}}
            elif parsed.path == "/api/v1/state":
                status, response = 200, envelope({"connected": True, "layers": {"heatmap": True}})
            elif parsed.path == "/api/v1/viewport" and self.command == "GET":
                status, response = 200, envelope({"startMs": 1, "endMs": 2, "viewportVersion": "9"})
            elif parsed.path == "/api/v1/candles":
                status, response = 200, envelope({"bars": [{"startMs": i, "close": i + 1} for i in range(100)], "nextStartMs": 101})
            elif parsed.path == "/api/v1/book":
                status, response = 200, envelope({"bestBid": 99, "bestAsk": 100, "spread": 1,
                                                  "bids": [[99 - i, 1] for i in range(100)],
                                                  "asks": [[100 + i, 1] for i in range(100)],
                                                  "bandLimited": True, "receivedAtMs": 1790596800000})
            elif parsed.path == "/api/v1/trades":
                status, response = 200, envelope({"timeBasis": "received",
                                                  "trades": [{"receivedAtMs": i, "price": 100 + i} for i in range(100)],
                                                  "summary": {"count": 100, "deltaQty": 5}, "retentionLimited": False})
            elif parsed.path == "/api/v1/screenshot":
                status, response = 200, {"ok": True, "path": "./screenshots/review.png", "target": "heatmap",
                                         "frameId": "f9", "viewportVersion": "9", "selectionEpoch": "3"}
            elif parsed.path.startswith("/api/v1/operations/"):
                status, response = 200, envelope({"operationId": parsed.path.rsplit("/", 1)[-1],
                                                  "status": behavior["operation_status"],
                                                  "viewportVersion": "9", "frameId": "f9" if behavior["operation_status"] == "rendered" else None})
            elif parsed.path in {"/api/v1/symbol", "/api/v1/timeframe", "/api/v1/viewport", "/api/v1/layers"}:
                status, response = 200, envelope({"operationId": f"o{len(requests)}", "status": "applied"})
            else:
                status, response = 404, {"ok": False, "error": {"code": "not_found", "message": "Unknown route"}}
            encoded = json.dumps(response).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        do_GET = respond
        do_POST = respond

    http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = Thread(target=http.serve_forever, daemon=True)
    worker.start()
    monkeypatch.setenv("COPNET_SENTINEL_URL", f"http://127.0.0.1:{http.server_port}")
    monkeypatch.setenv("COPENET_BARRICADE", "0")
    yield requests, behavior
    http.shutdown()
    http.server_close()
    worker.join(timeout=2)


def context(tmp_path: Path) -> ToolExecutionContext:
    return ToolExecutionContext(workdir=tmp_path, session_workspace_root=tmp_path, session_key="sentinel-test",
        provider_name="test", model="test", session_store=SessionStore(path=tmp_path / "index.json"),
        transcript_store=TranscriptStore(root_dir=tmp_path), providers={}, policy=policy_for_task_mode("none"))


@pytest.mark.asyncio
async def test_each_sentinel_read_preserves_meta_and_uses_expected_route(tmp_path: Path, server) -> None:
    requests, _ = server
    registry, ctx = ToolRegistry(), context(tmp_path)
    cases = [
        ("sentinel.state", {}, "/api/v1/state"),
        ("sentinel.viewport", {}, "/api/v1/viewport"),
        ("sentinel.candles", {"startMs": 1, "endMs": 1000, "timeframeMs": 60000, "limit": 100}, "/api/v1/candles"),
        ("sentinel.book", {"levels": 20}, "/api/v1/book"),
        ("sentinel.trades", {"windowMs": 60000, "limit": 100}, "/api/v1/trades"),
        ("sentinel.screenshot", {"name": "review", "target": "heatmap", "afterOperation": "o1", "waitMs": 100}, "/api/v1/screenshot"),
    ]
    for tool_id, args, route in cases:
        result = await registry.execute(ToolExecutionRequest(tool_id, args), ctx)
        assert result.ok, (tool_id, result.error)
        assert requests[-1][1] == route
        if tool_id == "sentinel.screenshot":
            assert result.output["path"] == "./screenshots/review.png"
            assert result.output["frameId"] == "f9"
            assert requests[-1][2]["afterOperation"] == ["o1"]
        else:
            assert result.output["meta"] == META
            assert json.loads(result.model_body)["meta"] == META
    assert requests[2][2] == {"startMs": ["1"], "endMs": ["1000"], "timeframeMs": ["60000"], "limit": ["100"]}


@pytest.mark.asyncio
async def test_large_sentinel_results_are_summarized_with_full_output_retained(tmp_path: Path, server, monkeypatch) -> None:
    monkeypatch.setenv("COPNET_MODEL_TOOL_RESULT_CHARS", "600")
    registry, ctx = ToolRegistry(), context(tmp_path)
    for tool_id, args, key in [
        ("sentinel.candles", {"startMs": 1, "endMs": 1000, "timeframeMs": 60000}, "bars"),
        ("sentinel.book", {}, "bids"), ("sentinel.trades", {}, "trades"),
    ]:
        result = await registry.execute(ToolExecutionRequest(tool_id, args), ctx)
        assert result.ok
        assert len(result.output["data"][key]) == 100
        assert len(json.dumps(result.model_body)) <= 600
        assert json.loads(result.model_body)["meta"] == META


@pytest.mark.asyncio
async def test_sentinel_view_requires_exact_approval_then_waits_and_screenshots(tmp_path: Path, server) -> None:
    requests, _ = server
    registry, ctx = ToolRegistry(), context(tmp_path)
    descriptor = registry.get_descriptor("sentinel.view.set")
    assert descriptor.requires_confirmation is True
    assert descriptor.side_effect == "write"
    assert descriptor.manifest_permission() == "policy_gated"
    assert {tool.id for tool in registry.list_tools()}.issuperset({"sentinel.view.set", "sentinel.state"})
    request = ToolExecutionRequest("sentinel.view.set", {"symbol": "eth-usd", "heatmapTimeframeMs": 60000,
        "viewport": {"startMs": 1, "endMs": 2}, "layers": {"heatmap": True}, "screenshot": True,
        "screenshotTarget": "heatmap"})
    blocked = await registry.execute(request, ctx)
    assert blocked.output["policyDecision"] == "approval_required"
    assert requests == []
    ctx.ephemeral["barricade_approved"] = {approval_key(request)}
    result = await registry.execute(request, ctx)
    assert result.ok, result.error
    assert result.output["frame"]["frameId"] == "f9"
    assert result.output["meta"] == META
    assert result.output["screenshot"]["frameId"] == "f9"
    assert [item[1] for item in requests] == [
        "/api/v1/symbol", "/api/v1/operations/o1", "/api/v1/timeframe", "/api/v1/operations/o3",
        "/api/v1/viewport", "/api/v1/operations/o5", "/api/v1/layers", "/api/v1/operations/o7",
        "/api/v1/screenshot",
    ]
    assert requests[0][3] == {"symbol": "ETH-USD"}
    assert requests[-1][2]["afterOperation"] == ["o7"]
    assert requests[-1][2]["waitMs"] == ["5000"]
    changed = ToolExecutionRequest("sentinel.view.set", {"symbol": "SOL-USD"})
    assert (await registry.execute(changed, ctx)).output["policyDecision"] == "approval_required"


@pytest.mark.asyncio
async def test_sentinel_view_approval_wrapper_classifies_and_resumes_exact_call(tmp_path: Path, server) -> None:
    requests, _ = server
    registry, ctx = ToolRegistry(), context(tmp_path)
    seen = []

    class Approval:
        async def await_tool_approval(self, **kwargs):
            seen.append(kwargs["request_payload"])
            return "approved", None

    async def emit(_name, _payload):
        pass

    execute = make_approval_gated_executor(registry.execute, orchestrator=Approval(), emit_event=emit,
        session_key="sentinel-test", run_id="run", abort_event=asyncio.Event())
    request = ToolExecutionRequest("sentinel.view.set", {"viewport": {"followLive": True}})
    result = await execute(request, ctx)
    assert result.ok
    assert seen[0]["actionClass"] == "sentinel_view_set"
    assert seen[0]["payload"] == request.arguments
    assert [item[1] for item in requests] == ["/api/v1/viewport", "/api/v1/operations/o1"]


@pytest.mark.asyncio
async def test_sentinel_operation_timeout_stops_following_controls(tmp_path: Path, server) -> None:
    requests, behavior = server
    behavior["operation_status"] = "applied"
    registry, ctx = ToolRegistry(), context(tmp_path)
    request = ToolExecutionRequest("sentinel.view.set", {"symbol": "ETH-USD", "layers": {"candles": True}, "waitMs": 10})
    ctx.ephemeral["barricade_approved"] = {approval_key(request)}
    result = await registry.execute(request, ctx)
    assert result.ok is False
    assert result.error == "render_timeout"
    assert result.output["meta"] == META
    assert [item[1] for item in requests] == ["/api/v1/symbol", "/api/v1/operations/o1"]
    assert requests[-1][2]["waitMs"] == ["10"]


@pytest.mark.asyncio
async def test_sentinel_api_error_envelope_and_gui_unavailable(tmp_path: Path, server, monkeypatch) -> None:
    _, behavior = server
    behavior["error"] = (409, "symbol_mismatch")
    registry, ctx = ToolRegistry(), context(tmp_path)
    result = await registry.execute(ToolExecutionRequest("sentinel.state"), ctx)
    assert result.error == "Sentinel rejected request"
    assert result.output["code"] == "symbol_mismatch"
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        unused_port = sock.getsockname()[1]
    monkeypatch.setenv("COPNET_SENTINEL_URL", f"http://127.0.0.1:{unused_port}")
    unavailable = await registry.execute(ToolExecutionRequest("sentinel.state"), ctx)
    assert unavailable.output["code"] == "gui_unavailable"
    assert "Sentinel GUI Agent API is unavailable" in unavailable.error


@pytest.mark.asyncio
async def test_sentinel_non_loopback_configuration_is_refused_without_io(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("COPNET_SENTINEL_URL", "http://example.com:17100")
    with pytest.raises(SentinelApiError, match="loopback"):
        sentinel_base_url()
    result = await ToolRegistry().execute(ToolExecutionRequest("sentinel.state"), context(tmp_path))
    assert result.output["code"] == "invalid_base_url"


@pytest.mark.asyncio
async def test_invalid_sentinel_control_is_rejected_before_approval(tmp_path: Path, server) -> None:
    requests, _ = server
    result = await ToolRegistry().execute(ToolExecutionRequest("sentinel.view.set", {"viewport": {"startMs": 1}}), context(tmp_path))
    assert result.output["code"] == "invalid_arguments"
    assert requests == []
