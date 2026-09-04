"""Chart evidence and editable documents use synthetic market data only."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy

import pytest

from copenet.core.market.chart_workspace import ChartStore

INSTRUMENT = {"instrumentId": "test:SYN", "symbol": "SYN", "assetClass": "equity", "source": "synthetic", "currency": None}


@pytest.fixture
def scene(tmp_path):
    store = ChartStore(tmp_path / "chart.sqlite3")
    document = store.workspace("primary", INSTRUMENT)["document"]
    capture = {
        "schemaVersion": 1, "viewId": "view-test", "viewRevision": 2, "instrument": INSTRUMENT,
        "timeframe": "D", "range": "1Y", "viewport": {"from": 100, "to": 200, "logicalFrom": 0.0, "logicalTo": 1.0},
        "selection": {"from": 100, "to": 100}, "settings": {"includeAccountContext": False},
        "resources": [{"key": "candles:D", "kind": "candles", "label": "Synthetic candles", "unit": "USD",
                       "status": "loaded", "rows": [{"t": 100, "c": 7.123456789}, {"t": 200, "c": None}],
                       "metadata": {"priceBasis": "split_adjusted", "timeframe": "D"}}],
        "documentId": document["documentId"], "documentRevision": 0,
    }
    observation = store.capture("session-test", "capture-test", capture)
    context = store.resolve_context("session-test", "run-test", {
        "observationId": observation["observationId"], "documentId": document["documentId"],
        "viewId": "view-test", "detail": "balanced", "access": "annotate",
    })
    return store, document, capture, observation, context


def drawing_request(document, observation, *, operation_id="create-one", object_id="level-one", revision=0):
    return {"documentId": document["documentId"], "expectedRevision": revision, "operationId": operation_id,
            "operations": [{"kind": "create", "object": {
                "id": object_id, "kind": "level", "anchors": [{"t": 100, "value": 7.123456789}],
                "timeframe": "D", "label": "Synthetic level", "color": "#abcdef", "visible": True,
                "rationale": "The selected candle", "evidence": [{"observationId": observation["observationId"], "resourceKey": "candles:D", "from": 100}],
            }}]}


def test_capture_is_exact_atomic_idempotent_and_immutable(scene):
    store, document, capture, observation, context = scene
    assert store.capture("session-test", "capture-test", capture) == observation
    row = store.read_resource(context, "candles:D", limit=1)
    assert row["rows"] == [{"t": 100, "c": 7.123456789}]
    assert row["nextOffset"] == 1
    assert store.read_resource(context, "candles:D", offset=1)["rows"] == [{"t": 200, "c": None}]
    capture["resources"][0]["rows"][0]["c"] = 999
    with pytest.raises(ValueError, match="different capture"):
        store.capture("session-test", "capture-test", capture)
    assert store.read_resource(context, "candles:D")["rows"][0]["c"] == 7.123456789
    store.apply(drawing_request(document, observation), context)
    assert store.read_resource(context, "drawings")["rows"] == []


def test_capture_rejects_wrong_identity_nonfinite_unknown_version_and_stale_drawings(scene):
    store, document, capture, observation, context = scene
    for change in ({"schemaVersion": 2}, {"documentRevision": 9}, {"instrument": {**INSTRUMENT, "symbol": "OTHER"}}):
        with pytest.raises(ValueError):
            store.capture("session-test", "invalid", {**capture, **change})
    malformed = deepcopy(capture)
    malformed["resources"][0]["rows"][0]["c"] = float("nan")
    with pytest.raises(ValueError, match="finite"):
        store.capture("session-test", "nonfinite", malformed)
    with store.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM observations").fetchone()[0] == 1


def test_batch_compare_and_swap_retries_and_actor_authority(scene):
    store, document, capture, observation, context = scene
    request = drawing_request(document, observation)
    receipt = store.apply(request, context)
    assert receipt == store.apply(request, context)
    assert receipt["document"]["objects"][0]["owner"] == {"kind": "agent", "sessionKey": "session-test", "runId": "run-test"}
    changed = deepcopy(request)
    changed["operations"][0]["object"]["label"] = "Changed retry"
    with pytest.raises(ValueError, match="different batch"):
        store.apply(changed, context)
    with pytest.raises(ValueError, match="revision conflict"):
        store.apply(drawing_request(document, observation, operation_id="different"), context)
    with pytest.raises(ValueError, match="different batch or actor"):
        store.apply(request)


def test_batch_failure_rolls_back_all_changes_and_evidence_binding(scene):
    store, document, capture, observation, context = scene
    request = drawing_request(document, observation)
    request["operations"].append({"kind": "delete", "objectId": "missing"})
    with pytest.raises(ValueError, match="unavailable"):
        store.apply(request, context)
    assert store.document(document["documentId"])["document"]["revision"] == 0
    with store.connect() as db:
        assert db.execute("SELECT bound FROM observations").fetchone()[0] == 0


def test_operator_takeover_blocks_agent_and_undo_conflicts(scene):
    store, document, capture, observation, context = scene
    receipt = store.apply(drawing_request(document, observation), context)
    store.apply({"documentId": document["documentId"], "expectedRevision": 1, "operationId": "operator-edit",
                 "operations": [{"kind": "update", "objectId": "level-one", "patch": {"label": "My level"}}]})
    update = {"documentId": document["documentId"], "expectedRevision": 2, "operationId": "agent-edit",
              "operations": [{"kind": "update", "objectId": "level-one", "patch": {"label": "Model overwrite"}}]}
    with pytest.raises(ValueError, match="operator-controlled"):
        store.apply(update, context)
    with pytest.raises(ValueError, match="later edit"):
        store.undo({"documentId": document["documentId"], "expectedRevision": 2,
                    "operationId": "undo-one", "batchId": receipt["batchId"]}, context)


def test_undo_preserves_unrelated_edits_and_dedupes(scene):
    store, document, capture, observation, context = scene
    receipt = store.apply(drawing_request(document, observation), context)
    store.apply(drawing_request(document, observation, operation_id="create-two", object_id="level-two", revision=1), context)
    undo = {"documentId": document["documentId"], "expectedRevision": 2, "operationId": "undo-one", "batchId": receipt["batchId"]}
    result = store.undo(undo, context)
    assert result == store.undo(undo, context)
    assert [obj["id"] for obj in result["document"]["objects"]] == ["level-two"]


def test_concurrent_document_writers_have_one_winner(scene):
    store, document, capture, observation, context = scene
    def attempt(number):
        try:
            return store.apply(drawing_request(document, observation, operation_id=f"op-{number}", object_id=f"obj-{number}"), context)["revision"]
        except ValueError as exc:
            return str(exc)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, [1, 2]))
    assert results.count(1) == 1
    assert sum("revision conflict" in str(result) for result in results) == 1


def test_observation_reads_and_draws_cannot_escape_turn_scope(scene):
    store, document, capture, observation, context = scene
    with pytest.raises(ValueError, match="this session"):
        store.observation(observation["observationId"], "other-session")
    with pytest.raises(ValueError, match="scope"):
        store.read_resource(context, "ungranted")
    request = drawing_request(document, observation)
    request["documentId"] = store.workspace("other", INSTRUMENT)["document"]["documentId"]
    with pytest.raises(ValueError, match="scope"):
        store.apply(request, context)
    request = drawing_request(document, observation)
    request["operations"][0]["object"]["anchors"][0]["t"] = 300
    with pytest.raises(ValueError, match="captured candle timestamps"):
        store.apply(request, context)


def test_render_receipts_distinguish_saved_from_visible(scene):
    store, document, capture, observation, context = scene
    receipt = store.apply(drawing_request(document, observation), context)
    assert receipt["renderStatus"] == "pending"
    rendered = store.rendered({"documentId": document["documentId"], "viewId": "view-test", "revision": 1,
                               "status": "hidden", "objectIds": [], "reason": "Different timeframe"})
    assert rendered["status"] == "hidden"
    assert store.document(document["documentId"])["renderStatus"][0]["status"] == "hidden"
    with pytest.raises(ValueError, match="unsaved"):
        store.rendered({**{key: value for key, value in rendered.items() if key != "receivedAt"}, "revision": 2})


def test_capacity_orphan_cleanup_and_run_references_survive_restart(scene):
    store, document, capture, observation, context = scene
    store.reserve_admission("session-test", "request-one", "fingerprint", "run-test", observation["observationId"])
    capture["viewRevision"] += 1
    orphan = store.capture("session-test", "orphan", capture)
    assert store.cleanup_orphans(now=observation["capturedAt"] + 86402) == 1
    with pytest.raises(ValueError, match="unavailable"):
        store.observation(orphan["observationId"], "session-test")
    restarted = ChartStore(store.path)
    assert restarted.observation(observation["observationId"], "session-test") == observation
    assert restarted.reserve_admission("session-test", "request-one", "fingerprint", "ignored-run", observation["observationId"])["runId"] == "run-test"
    with pytest.raises(ValueError, match="different content"):
        restarted.reserve_admission("session-test", "request-one", "changed", "run-2", observation["observationId"])
    store.capacity_bytes = 1
    capture["resources"][0]["rows"][0]["c"] = 20
    with pytest.raises(ValueError, match="capacity"):
        store.capture("session-test", "overcapacity", capture)


def test_detail_projection_keeps_exact_selected_candle_and_account_scope(scene):
    store, document, capture, observation, context = scene
    from dataclasses import replace
    for detail in ("quick", "balanced", "deep"):
        result = store.context_payload(replace(context, detail=detail))
        assert result["samples"][0]["rows"] == [{"t": 100, "c": 7.123456789}]
        assert result["estimatedTokens"] < result["budget"]["initialTokens"]
    account = {"key": "account", "kind": "panel", "label": "Synthetic account", "status": "loaded",
               "rows": [{"example": 10}], "metadata": {"accountContext": True}}
    capture["resources"].append(account)
    with pytest.raises(ValueError, match="Account-derived"):
        store.capture("session-test", "account-no-consent", capture)
    capture["settings"]["includeAccountContext"] = True
    old = store.capture("session-test", "account-consent", capture)
    with pytest.raises(ValueError, match="scope"):
        store.read_resource(context, "account", observation_id=old["observationId"])


@pytest.mark.asyncio
async def test_chart_rpc_session_checks_exact_capture_and_document_events(scene):
    from types import SimpleNamespace
    from copenet.host.rpc_market_chart import MARKET_CHART_HANDLERS
    store, document, capture, observation, context = scene
    sessions = {"session-test": SimpleNamespace(archived=False), "archived": SimpleNamespace(archived=True)}
    orchestrator = SimpleNamespace(_chart_store=store, _session_store=SimpleNamespace(get=sessions.get))
    frames = []
    async def send(frame):
        frames.append(frame)
    await MARKET_CHART_HANDLERS["market.chart.capture"]("rpc-1", {
        "sessionKey": "session-test", "captureId": "rpc-capture", "capture": capture,
    }, send, orchestrator)
    assert frames[0]["ok"] is True
    assert frames[0]["payload"]["provenance"] == "browser_capture"
    with pytest.raises(ValueError, match="archived"):
        await MARKET_CHART_HANDLERS["market.chart.capture"]("rpc-2", {
            "sessionKey": "archived", "captureId": "rpc-archived", "capture": capture,
        }, send, orchestrator)
    frames.clear()
    await MARKET_CHART_HANDLERS["market.chart.apply"]("rpc-3", drawing_request(document, observation), send, orchestrator)
    assert frames[0]["payload"]["document"]["objects"][0]["owner"]["kind"] == "operator"
    assert frames[1]["event"] == "market.chart.document"
    assert frames[1]["payload"]["documentId"] == document["documentId"]


@pytest.mark.asyncio
async def test_chart_tools_enforce_run_binding_and_read_budget(scene):
    from types import SimpleNamespace
    from copenet.core.tools.contracts import ToolBlockedError, ToolExecutionRequest
    from copenet.core.tools.handlers.market_chart import HANDLERS
    store, document, capture, observation, binding = scene
    context = SimpleNamespace(market_context=binding, chart_store=store,
                              session_key=binding.session_key, run_id=binding.run_id, ephemeral={})
    request = ToolExecutionRequest(tool_id="market.chart.read", arguments={"resourceKey": "candles:D", "limit": 1})
    for _ in range(8):
        result = await HANDLERS[request.tool_id](request, context)
        assert result.output["rows"][0]["c"] == 7.123456789
    with pytest.raises(ValueError, match="budget exhausted"):
        await HANDLERS[request.tool_id](request, context)
    context.run_id = "wrong-run"
    with pytest.raises(ToolBlockedError, match="executing run"):
        await HANDLERS[request.tool_id](request, context)


def test_resource_references_remain_indexed_beyond_artifact_history_limit(scene):
    store, document, capture, observation, context = scene
    for index in range(505):
        capture["viewRevision"] = index + 3
        store.capture("session-test", f"capture-{index}", capture)
    assert store.read_resource(context, "candles:D")["rows"][0]["c"] == 7.123456789
    with store.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM resources").fetchone()[0] == 2
        assert db.execute("SELECT COUNT(*) FROM observations").fetchone()[0] == 506


def test_document_commit_failure_cannot_leave_a_revision_without_receipt(scene):
    store, document, capture, observation, context = scene
    import sqlite3
    with store.connect() as db:
        db.execute("CREATE TRIGGER fail_operation BEFORE INSERT ON operations BEGIN SELECT RAISE(ABORT,'injected failure'); END")
    with pytest.raises(sqlite3.IntegrityError, match="injected failure"):
        store.apply(drawing_request(document, observation), context)
    saved = store.document(document["documentId"])
    assert saved["document"]["revision"] == 0
    assert saved["document"]["objects"] == []
    assert saved["batches"] == []


def test_drawing_timeframe_and_comparison_scope_are_enforced(scene):
    store, document, capture, observation, context = scene
    capture["timeframe"] = "W"
    weekly = store.capture("session-test", "weekly", capture)
    weekly_context = store.resolve_context("session-test", "weekly-run", {
        "observationId": weekly["observationId"], "documentId": document["documentId"], "viewId": "view-test", "access": "annotate"})
    request = drawing_request(document, weekly)
    request["operations"][0]["object"]["timeframe"] = "W"
    with pytest.raises(ValueError, match="captured candle timestamps"):
        store.apply(request, weekly_context)
    capture["timeframe"] = "D"
    capture["settings"]["comparisonMode"] = True
    comparison = store.capture("session-test", "comparison", capture)
    comparison_context = store.resolve_context("session-test", "compare-run", {
        "observationId": comparison["observationId"], "documentId": document["documentId"], "viewId": "view-test", "access": "annotate"})
    with pytest.raises(ValueError, match="comparison axes"):
        store.apply(drawing_request(document, comparison), comparison_context)


def test_nested_metadata_reads_preserve_exact_values_and_pagination(scene):
    store, document, capture, observation, context = scene
    capture["resources"][0]["metadata"]["filings"] = [{"value": index / 17, "note": "synthetic"} for index in range(200)]
    captured = store.capture("session-test", "metadata", capture)
    result = store.read_resource(context, "candles:D", offset=101, limit=2,
                                 observation_id=captured["observationId"], metadata_path=["filings"])
    assert result["rows"][0]["value"] == 101 / 17
    assert result["nextOffset"] == 103
    assert result["totalCount"] == 200
    scalar = store.read_resource(context, "candles:D", observation_id=captured["observationId"], metadata_path=["filings", 101, "value"])
    assert scalar["rows"] == [{"value": 101 / 17}]


@pytest.mark.asyncio
async def test_evidence_rpc_checks_session_ownership_and_account_consent(scene):
    from types import SimpleNamespace
    from copenet.host.rpc_market_chart import handle_chart_read
    store, document, capture, observation, context = scene
    frames = []
    async def send(frame):
        frames.append(frame)
    orchestrator = SimpleNamespace(_chart_store=store, _session_store=SimpleNamespace(get=lambda key: SimpleNamespace(archived=True)))
    args = {"sessionKey": "session-test", "observationId": observation["observationId"], "resourceKey": "candles:D", "limit": 1}
    await handle_chart_read("read", args, send, orchestrator)
    assert frames[-1]["payload"]["rows"][0]["c"] == 7.123456789
    with pytest.raises(ValueError, match="this session"):
        await handle_chart_read("wrong", {**args, "sessionKey": "other"}, send, orchestrator)
    capture["settings"]["includeAccountContext"] = True
    capture["resources"].append({"key": "account", "kind": "panel", "label": "Synthetic account", "status": "loaded",
                                "rows": [{"example": 1}], "metadata": {"accountContext": True}})
    account = store.capture("session-test", "account-allowed", capture)
    args = {**args, "observationId": account["observationId"], "resourceKey": "account"}
    with pytest.raises(ValueError, match="scope"):
        await handle_chart_read("excluded", args, send, orchestrator)
    await handle_chart_read("included", {**args, "includeAccountContext": True}, send, orchestrator)
    assert frames[-1]["payload"]["rows"] == [{"example": 1}]


def test_default_projection_samples_recent_view_rows_and_discloses_offsets(scene):
    store, document, capture, observation, context = scene
    from dataclasses import replace
    capture["selection"] = None
    capture["viewport"].update({"from": 100, "to": 299})
    capture["resources"][0]["rows"] = [{"t": value, "c": value / 13} for value in range(100, 300)]
    observation = store.capture("session-test", "recent-window", capture)
    current = replace(context, observation_id=observation["observationId"])
    projected = store.context_payload(current)
    sample = projected["samples"][0]
    assert sample["rows"][0]["t"] == 260
    assert sample["rows"][-1]["t"] == 299
    assert sample["offset"] == 160
    assert sample["nextOffset"] is None
    assert sample["matchedCount"] == 200


def test_maximum_resource_inventory_respects_estimated_detail_budget(scene):
    from dataclasses import replace
    store, document, capture, observation, context = scene
    capture["settings"]["indicators"] = "x" * 40000
    capture["resources"] = [{"key": f"{index:02d}" + "k" * 118, "kind": "panel", "label": "l" * 160,
                             "unit": "u" * 80, "status": "loaded", "rows": [], "metadata": {}}
                            for index in range(31)]
    observation = store.capture("session-test", "inventory", capture)
    current = store.resolve_context("session-test", "inventory-run", {
        "observationId": observation["observationId"], "documentId": document["documentId"], "viewId": "view-test", "detail": "quick"})
    result = store.context_payload(current)
    assert result["estimatedTokens"] <= 2000
    assert len(result["resources"]) == 32
    assert result["manifestOmissions"]


@pytest.mark.asyncio
async def test_operator_evidence_link_survives_manual_takeover_and_new_session(scene):
    from types import SimpleNamespace
    from copenet.host.rpc_market_chart import handle_chart_read
    store, document, capture, observation, context = scene
    store.apply(drawing_request(document, observation), context)
    store.apply({"documentId": document["documentId"], "expectedRevision": 1, "operationId": "takeover",
                 "operations": [{"kind": "update", "objectId": "level-one", "patch": {"label": "Operator level"}}]})
    assert store.document(document["documentId"])["document"]["objects"][0]["owner"] == {"kind": "operator"}
    frames = []
    async def send(frame):
        frames.append(frame)
    orchestrator = SimpleNamespace(_chart_store=store)
    params = {"documentId": document["documentId"], "observationId": observation["observationId"], "resourceKey": "candles:D", "limit": 1}
    await handle_chart_read("evidence", params, send, orchestrator)
    assert frames[-1]["payload"]["rows"][0]["c"] == 7.123456789
    with pytest.raises(ValueError, match="not referenced"):
        await handle_chart_read("unreferenced", {**params, "resourceKey": "drawings"}, send, orchestrator)
