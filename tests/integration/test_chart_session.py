"""Chart evidence travels through normal sessions; authority never escapes that turn."""
from __future__ import annotations

import asyncio
from dataclasses import replace
import json

import pytest

from copenet.core.market.chart_workspace import get_chart_store
from copenet.core.orchestrator import Orchestrator
from copenet.core.orchestrator.market_context import admit_chart_turn, resolve_market_context
from copenet.core.orchestrator.requests import ChatSendRequest, MarketContextRequest
from copenet.core.sessions import SessionStore, TranscriptStore
from copenet.providers import ProviderEvent


@pytest.fixture(autouse=True)
def isolated_chart_security():
    from copenet.core.tools.barricade import reset_session_security
    reset_session_security("chart-session")
    yield
    reset_session_security("chart-session")


class ChartProvider:
    name = "chart-test"
    display_name = "Chart test"

    def __init__(self, calls=(), *, name=None):
        self.calls = list(calls)
        self.messages = []
        self.prompts = []
        self.tool_names = []
        if name:
            self.name = name

    async def describe(self):
        return {"id": self.name, "available": True, "capabilities": {
            "chat": True, "streaming": True, "toolCalls": self.name != "claude-cli",
            "promptedToolUse": self.name != "claude-cli",
        }}

    async def list_models(self):
        return []

    async def run(self, prompt, provider_session_id, abort_event, model=None, system_prompt=None):
        self.prompts.append(prompt)
        yield ProviderEvent(kind="delta", text="Chart inspected", provider_session_id="chart-provider-session")
        yield ProviderEvent(kind="final")

    async def chat_completion(self, *, messages, model, tools=None, tool_choice=None):
        self.messages.append(messages)
        self.tool_names.append([tool["function"]["name"] for tool in tools or []])
        if self.calls:
            name, args = self.calls.pop(0)
            if callable(args):
                args = args(messages)
            return {"choices": [{"finish_reason": "tool_calls", "message": {"role": "assistant", "content": "", "tool_calls": [{
                "id": f"call-{len(self.messages)}", "type": "function",
                "function": {"name": name, "arguments": json.dumps(args)},
            }]}}]}
        return {"choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": "Chart inspected"}}]}


def setup_chart(tmp_path, provider=None, *, external_prose=False):
    provider = provider or ChartProvider()
    orch = Orchestrator(session_store=SessionStore(path=tmp_path / "index.json"),
                        transcript_store=TranscriptStore(root_dir=tmp_path), sessions_dir=tmp_path,
                        providers={provider.name: provider})
    store = get_chart_store(orch)
    instrument = {"instrumentId": "yahoo:TEST", "symbol": "TEST", "assetClass": "equity", "source": "yahoo", "currency": "USD"}
    doc = store.workspace("test-market", instrument)["document"]
    resources = [{"key": "candles:D", "kind": "candles", "label": "Daily", "status": "loaded", "metadata": {"basis": "split-only", "timeframe": "D"},
                  "rows": [{"t": 1720000000, "o": 10.0, "h": 12.0, "l": 9.0, "c": 11.125, "v": 1000.0}]}]
    if external_prose:
        resources.append({"key": "panel", "kind": "panel", "label": "Research", "status": "loaded", "metadata": {}, "rows": [{"text": "Synthetic external filing excerpt"}]})
    capture = {"schemaVersion": 1, "viewId": "view-test", "viewRevision": 1, "instrument": instrument,
               "timeframe": "D", "range": "1Y", "viewport": {"from": 1720000000, "to": 1720000000, "logicalFrom": 0.0, "logicalTo": 0.0},
               "selection": None, "settings": {}, "documentId": doc["documentId"], "documentRevision": 0, "resources": resources}
    observation = store.capture("chart-session", "capture-test", capture)
    request = ChatSendRequest(session_key="chart-session", message="Inspect the selected candle", provider=provider.name,
                              idempotency_key="chart-run", market_context=MarketContextRequest(
                                  observation["observationId"], doc["documentId"], "view-test", access="annotate"))
    return orch, provider, store, request


async def collect(orch, request, emit_event=None):
    events = []
    async def emit(payload):
        events.append(payload)
    result = await orch.send_chat(request, emit, emit_event=emit_event)
    return result, events


@pytest.mark.asyncio
async def test_chart_context_survives_normal_run_replay_and_retry(tmp_path):
    orch, provider, store, request = setup_chart(tmp_path)
    result, _ = await collect(orch, request)
    assert result["status"] == "ok"
    sent = json.dumps(provider.messages)
    assert "11.125" in sent and request.market_context.observation_id in sent
    assert provider.tool_names[0] and all(name.startswith("market.chart.") for name in provider.tool_names[0])
    history = orch.history(session_key=request.session_key)
    assert history[0]["content"] == request.message
    assert history[0]["marketContext"]["observationId"] == request.market_context.observation_id
    assert history[0]["marketContext"]["symbol"] == "TEST"
    assert history[0]["marketContext"]["timeframe"] == "D"
    run = orch._run_store.get(request.session_key, request.idempotency_key)
    assert run.metadata["marketContext"]["documentId"] == request.market_context.document_id
    assert any(item.type == "chart_observation" for item in orch._artifact_store.list_for_session(request.session_key))
    calls = len(provider.messages)
    assert (await collect(orch, request))[0]["status"] == "completed"
    assert len(provider.messages) == calls
    with pytest.raises(ValueError, match="different content"):
        await collect(orch, replace(request, message="Changed request"))
    await collect(orch, replace(request, idempotency_key="second-chart-run", message="Explain the same candle"))
    assert "Historical chart observation" in json.dumps(provider.messages[-1])


@pytest.mark.asyncio
async def test_interrupted_admission_never_redispatches_after_restart(tmp_path):
    orch, provider, store, request = setup_chart(tmp_path)
    context = resolve_market_context(orch, request, request.idempotency_key)
    admit_chart_turn(orch, request, context)
    restarted = Orchestrator(session_store=SessionStore(path=tmp_path / "index.json"),
                             transcript_store=TranscriptStore(root_dir=tmp_path), sessions_dir=tmp_path,
                             providers={provider.name: provider})
    result, events = await collect(restarted, request)
    assert result["status"] == "interrupted"
    assert not events and not provider.messages and not provider.prompts
    assert not restarted.history(session_key=request.session_key)


@pytest.mark.asyncio
async def test_wrong_observation_owner_fails_before_provider_or_transcript(tmp_path):
    orch, provider, store, request = setup_chart(tmp_path)
    with pytest.raises(ValueError, match="unavailable for this session"):
        await collect(orch, replace(request, session_key="other-session"))
    assert not provider.messages and not provider.prompts
    assert not orch.history(session_key="other-session")


@pytest.mark.asyncio
async def test_resumed_claude_receives_current_observation(tmp_path):
    orch, provider, store, request = setup_chart(tmp_path, ChartProvider(name="claude-cli"))
    await collect(orch, request)
    await collect(orch, replace(request, idempotency_key="next-run", message="Inspect again"))
    assert len(provider.prompts) == 2
    assert "11.125" in provider.prompts[1] and request.market_context.observation_id in provider.prompts[1]
    assert "Conversation so far" not in provider.prompts[1]


@pytest.mark.parametrize("raw", [{}, {"observationId": 3}, {"observationId": "o", "documentId": "d", "viewId": "v", "access": "full-access"},
                                {"observationId": "o", "documentId": "d", "viewId": "v", "actor": "operator"}])
def test_market_context_rejects_invalid_authority(raw):
    with pytest.raises(ValueError):
        MarketContextRequest.from_dict(raw)


def level_batch(request, operation_id="draw-level", revision=0):
    return {"documentId": request.market_context.document_id, "operationId": operation_id, "expectedRevision": revision,
            "operations": [{"kind": "create", "object": {
                "id": "support", "kind": "level", "anchors": [{"t": 1720000000, "value": 9.0}],
                "timeframe": "D", "label": "Captured low", "color": "#10b981", "visible": True,
                "rationale": "The selected candle low is 9", "evidence": [{
                    "observationId": request.market_context.observation_id, "resourceKey": "candles:D", "from": 1720000000, "to": 1720000000,
                }],
            }}]}


@pytest.mark.asyncio
async def test_native_chart_loop_inspects_draws_revises_and_undoes(tmp_path):
    orch, provider, store, request = setup_chart(tmp_path)
    def undo_latest(messages):
        latest = store.document(request.market_context.document_id)
        return {"documentId": request.market_context.document_id, "expectedRevision": 2,
                "operationId": "undo-revision", "batchId": latest["batches"][0]["batchId"]}
    provider.calls = [
        ("market.chart.context", {}),
        ("market.chart.read", {"resourceKey": "candles:D", "limit": 1}),
        ("market.chart.apply", level_batch(request)),
        ("market.chart.document", {}),
        ("market.chart.apply", {"documentId": request.market_context.document_id, "expectedRevision": 1,
                                "operationId": "revise-level", "operations": [{"kind": "update", "objectId": "support", "patch": {"label": "Revised support"}}]}),
        ("market.chart.undo", undo_latest),
    ]
    result, events = await collect(orch, request)
    assert result["status"] == "ok"
    document = store.document(request.market_context.document_id)["document"]
    assert document["revision"] == 3
    assert document["objects"][0]["label"] == "Captured low"
    assert document["objects"][0]["owner"]["sessionKey"] == request.session_key
    run = orch._run_store.get(request.session_key, request.idempotency_key)
    assert len(run.tool_steps) == 6 and all(step["ok"] for step in run.tool_steps)
    assert any(event.get("toolExecution") for event in events)


@pytest.mark.asyncio
async def test_external_prose_requires_exact_batch_approval_and_preserves_scope(tmp_path):
    orch, provider, store, request = setup_chart(tmp_path, external_prose=True)
    batch = level_batch(request)
    provider.calls = [("market.chart.apply", batch)]
    approvals = []
    async def approve(name, payload):
        if name == "approval.pending":
            approval = payload["approval"]
            approvals.append(approval)
            orch.decide_approval(approval_id=approval["approvalId"], decision="approved_always")
    result, _ = await collect(orch, request, approve)
    assert result["status"] == "ok"
    assert len(approvals) == 1
    assert approvals[0]["proposedAction"]["payload"] == batch
    assert "shell" not in approvals[0]["proposedAction"]["description"].lower()
    assert store.document(request.market_context.document_id)["document"]["revision"] == 1
    assert orch.history(session_key=request.session_key)[0]["marketContext"]["hasExternalProse"]


@pytest.mark.asyncio
async def test_chart_direct_execution_cannot_escape_even_with_full_access(tmp_path):
    from copenet.core.orchestrator.market_context import chart_policy, chart_tool_ids
    from copenet.core.tools import ToolExecutionContext, ToolExecutionRequest, policy_for_task_mode
    orch, provider, store, request = setup_chart(tmp_path)
    bound = resolve_market_context(orch, request, request.idempotency_key)
    ctx = ToolExecutionContext(workdir=tmp_path, session_workspace_root=tmp_path, session_key=request.session_key,
                               provider_name=provider.name, model=None, session_store=orch._session_store,
                               transcript_store=orch._transcript_store, providers={},
                               policy=chart_policy(policy_for_task_mode("full-access"), bound),
                               market_context=bound, chart_store=store, run_id=bound.run_id,
                               allowed_tool_ids=chart_tool_ids(bound))
    for tool_id in ("shell.exec", "files.read", "market.ticker", "memory.read"):
        result = await orch._tool_registry.execute(ToolExecutionRequest(tool_id=tool_id, arguments={}), ctx)
        assert not result.ok and "scope" in result.error
    read_only = replace(ctx, market_context=replace(bound, access="read"))
    denied = await orch._tool_registry.execute(ToolExecutionRequest(tool_id="market.chart.apply", arguments=level_batch(request)), read_only)
    assert not denied.ok
    no_binding = replace(ctx, market_context=None)
    denied = await orch._tool_registry.execute(ToolExecutionRequest(tool_id="market.chart.read", arguments={"resourceKey": "candles:D"}), no_binding)
    assert not denied.ok
    assert store.document(bound.document_id)["document"]["revision"] == 0


@pytest.mark.asyncio
async def test_chart_rpc_validates_before_started_response(tmp_path):
    from copenet.host.rpc_chat import handle_chat_send
    orch, provider, store, request = setup_chart(tmp_path)
    frames, tasks = [], set()
    async def send(frame):
        frames.append(frame)
    await handle_chat_send("bad", {"sessionKey": "other-session", "message": "hello", "provider": provider.name,
                                    "idempotencyKey": "bad-run", "marketContext": request.market_context.to_dict()}, send, tasks, orch)
    await asyncio.gather(*tasks)
    assert len(frames) == 1 and frames[0]["ok"] is False
    assert not provider.messages
    await handle_chat_send("good", {"sessionKey": request.session_key, "message": request.message, "provider": provider.name,
                                     "idempotencyKey": request.idempotency_key, "marketContext": request.market_context.to_dict()}, send, tasks, orch)
    await asyncio.gather(*tasks)
    responses = [frame for frame in frames if frame.get("id") == "good"]
    assert len(responses) == 1 and responses[0]["payload"]["status"] == "started"


@pytest.mark.asyncio
@pytest.mark.parametrize("decision", ["rejected", "aborted", "revision_changed"])
async def test_chart_approval_never_bypasses_rejection_abort_or_revision(tmp_path, decision):
    orch, provider, store, request = setup_chart(tmp_path, external_prose=True)
    provider.calls = [("market.chart.apply", level_batch(request))]
    async def decide(name, payload):
        if name != "approval.pending":
            return
        if decision == "revision_changed":
            manual = level_batch(request, "operator-level")
            manual["operations"][0]["object"]["id"] = "operator-support"
            store.apply(manual)
        if decision == "aborted":
            orch.abort(session_key=request.session_key, run_id=request.idempotency_key)
        orch.decide_approval(approval_id=payload["approval"]["approvalId"],
                             decision="rejected" if decision == "rejected" else "approved")
    await collect(orch, request, decide)
    objects = store.document(request.market_context.document_id)["document"]["objects"]
    assert not any(obj["id"] == "support" for obj in objects)
    if decision == "revision_changed":
        assert objects[0]["owner"]["kind"] == "operator"


@pytest.mark.asyncio
async def test_historical_chart_tool_results_replay_as_refs_without_rewriting_transcript(tmp_path):
    orch, provider, store, request = setup_chart(tmp_path)
    provider.calls = [("market.chart.read", {"resourceKey": "candles:D", "limit": 1})]
    await collect(orch, request)
    historical = orch.history(session_key=request.session_key)[1]
    original = next(part["toolExecution"]["replayOutput"] for part in historical["parts"] if part["kind"] == "tool_result")
    assert "11.125" in original
    await collect(orch, replace(request, idempotency_key="replay-run", message="Continue"))
    replay = str(provider.messages[-1])
    assert "Historical chart result" in replay
    assert replay.count("11.125") == 1  # Current observation only; historical raw rows are not replayed.
    persisted = orch.history(session_key=request.session_key)[1]
    assert next(part["toolExecution"]["replayOutput"] for part in persisted["parts"] if part["kind"] == "tool_result") == original
