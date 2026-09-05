"""CSV reaches each provider lane while inspection and stored evidence stay structured."""
import json

import pytest

from copenet.core.tools import ToolExecutionResult
from test_chart_session import setup_chart, collect
from test_tool_loop_contract import _run_contract, _ScriptedTurn, _call


@pytest.mark.asyncio
@pytest.mark.parametrize("loop_kind", ["native", "responses", "prompted"])
async def test_all_tool_loops_deliver_csv_and_preserve_result_identity(tmp_path, loop_kind):
    model_body = 'Frozen evidence.\n```csv\nt,c\n1720000000,11.125\n```'

    async def execute(request, context):
        return ToolExecutionResult(tool_id=request.tool_id, ok=True, summary="Exact table",
                                   output={"rows": [{"t": 1720000000, "c": 11.125}]}, model_body=model_body)

    provider, events, _ = await _run_contract(loop_kind=loop_kind, tmp_path=tmp_path, executor=execute,
                                            turns=[_ScriptedTurn(calls=[_call()]), _ScriptedTurn(text="Read it")])
    if loop_kind == "prompted":
        assert json.dumps(model_body) in provider.seen_prompts[1]
    else:
        messages = provider.seen_messages[1]
        raw = next(message["content"] for message in messages if message.get("role") == "tool") if loop_kind == "native" else next(
            message["output"] for message in messages if message.get("type") == "function_call_output")
        envelope = json.loads(raw)
        assert envelope["body"] == model_body
        assert envelope["callId"] and envelope["ok"] is True and envelope["summary"] == "Exact table"
    runtime = next(event.metadata["toolResult"] for event in events if event.metadata and "toolResult" in event.metadata)
    assert runtime["body"] == model_body


@pytest.mark.asyncio
async def test_chart_session_receives_csv_initial_context_and_exact_read(tmp_path):
    orch, provider, store, request = setup_chart(tmp_path)
    provider.calls = [("market.chart.read", {"resourceKey": "candles:D", "limit": 1})]
    result, _ = await collect(orch, request)
    assert result["status"] == "ok"
    initial = next(message["content"] for message in provider.messages[0] if message["role"] == "user")
    assert request.message in initial and "```csv\nt,o,h,l,c,v\n" in initial
    assert initial.index(request.message) < initial.index("```csv")
    assert '"rows":' not in initial
    tool = next(message["content"] for message in provider.messages[-1] if message["role"] == "tool")
    assert "```csv\nt,o,h,l,c,v\n" in json.loads(tool)["body"]
    assert '"rows":' not in json.loads(tool)["body"]
    replay = next(part["toolExecution"]["replayOutput"] for part in orch.history(session_key=request.session_key)[1]["parts"]
                  if part["kind"] == "tool_result")
    assert "```csv\nt,o,h,l,c,v\n" in replay
    observation_artifact = next(item for item in orch._artifact_store.list_for_session(request.session_key) if item.type == "chart_observation")
    # Artifact identity is retained for inspection; canonical exact resource reads still return objects.
    assert observation_artifact.artifact_id
    bound = store.resolve_context(request.session_key, "inspect", request.market_context.to_dict())
    assert store.read_resource(bound, "candles:D")["rows"][0]["c"] == 11.125
