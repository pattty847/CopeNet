"""Web research reaches ordinary chart turns without widening forecast or write authority."""
from dataclasses import replace
import json

import pytest

from copenet.core.market.chart_workspace.authorization import chart_tool_ids
from copenet.core.orchestrator.market_context import chart_policy, resolve_market_context
from copenet.core.tools import ToolExecutionContext, ToolExecutionRequest, policy_for_task_mode
from copenet.core.tools.barricade import reset_session_security
from copenet.core.tools.handlers import web
from copenet.core.web_ingest import WebExtractResult
from test_chart_session import collect, level_batch, setup_chart


SOURCE_URL = "https://example.com/company/announcement"
SOURCE_TEXT = "Synthetic company announced a new store on 2024-07-03. Opening effective 2024-08-01."


@pytest.fixture(autouse=True)
def isolated_web(monkeypatch):
    monkeypatch.setenv("COPENET_BARRICADE", "1")
    monkeypatch.delenv("COPNET_WEB_FETCH_ALLOWLIST", raising=False)
    reset_session_security("chart-session")
    calls = []

    def search(query, *, limit, news):
        calls.append(("search", query))
        return [{"title": "Synthetic company announcement", "url": SOURCE_URL, "snippet": SOURCE_TEXT}]

    async def fetch(self, *, url, max_chars):
        calls.append(("fetch", url))
        return WebExtractResult(url=url, title="Synthetic company announcement", text=SOURCE_TEXT,
                                markdown=SOURCE_TEXT, excerpt=SOURCE_TEXT, word_count=len(SOURCE_TEXT.split()))

    # Replace external I/O only; execute the actual web handlers and approval gates.
    monkeypatch.setattr(web, "_search_via_brave", search)
    monkeypatch.setattr(web.WebIngestionService, "extract_url", fetch)
    yield calls
    reset_session_security("chart-session")


@pytest.mark.asyncio
@pytest.mark.parametrize("access", ["read", "annotate"])
async def test_chart_searches_reads_and_retains_sourced_date_label(tmp_path, isolated_web, access):
    orch, provider, store, request = setup_chart(tmp_path)
    request = replace(request, message="Research significant company dates and mark them on this chart.",
                      market_context=replace(request.market_context, access=access))
    batch = level_batch(request)
    obj = batch["operations"][0]["object"]
    obj.update(kind="label", label="2024-07-03 · Store announcement",
               rationale=f"Announcement date, not the opening date. Source: {SOURCE_URL}")
    obj["anchors"] = [{"t": 1720000000, "value": 11.125, "evidenceField": "c"}]
    provider.calls = [
        ("web.search", {"query": "TEST company significant dates July 2024"}),
        ("web.fetch", {"url": SOURCE_URL}),
        ("market.chart.read", {"resourceKey": "candles:D", "limit": 1}),
        ("market.chart.document", {}),
    ]
    if access == "annotate":
        provider.calls.append(("market.chart.apply", batch))
    approvals = []

    async def approve(name, payload):
        if name == "approval.pending":
            assert payload["approval"]["actionClass"] == (
                "network_side_effect" if payload["approval"]["toolId"] == "web.fetch" else "chart_annotation"
            )
            approvals.append(payload["approval"]["proposedAction"])
            orch.decide_approval(approval_id=payload["approval"]["approvalId"], decision="approved")

    result, events = await collect(orch, request, approve)
    assert result["status"] == "ok"
    assert isolated_web == [("search", "TEST company significant dates July 2024"), ("fetch", SOURCE_URL)]
    assert {"web.search", "web.fetch"} <= set(provider.tool_names[0])
    assert ("market.chart.apply" in provider.tool_names[0]) == (access == "annotate")
    assert [action["description"] for action in approvals] == (
        ["Run web.fetch", "Run market.chart.apply"] if access == "annotate" else ["Run web.fetch"]
    )
    assert approvals[0]["payload"] == {"url": SOURCE_URL}
    document = store.document(request.market_context.document_id)["document"]
    if access == "annotate":
        assert approvals[1]["payload"] == batch
        saved = document["objects"][0]
        assert saved["kind"] == "label" and saved["label"] == obj["label"]
        assert SOURCE_URL in saved["rationale"]
        assert saved["anchors"][0]["verified"] == "exact"
        assert saved["owner"]["sessionKey"] == request.session_key
    else:
        assert document["revision"] == 0 and not document["objects"]
    run = orch._run_store.get(request.session_key, request.idempotency_key)
    assert all(step["ok"] for step in run.tool_steps)
    web_steps = [step for step in run.tool_steps if step["toolId"].startswith("web.")]
    assert len(web_steps) == 2
    assert [step["preview"]["type"] for step in web_steps] == ["web_search", "web_doc"]
    assert web_steps[1]["preview"]["url"] == SOURCE_URL
    assert SOURCE_TEXT in json.dumps(orch.history(session_key=request.session_key))
    assert any(event.get("toolExecution", {}).get("toolId") == "web.fetch" for event in events)
    bound = resolve_market_context(orch, request, request.idempotency_key)
    assert store.read_resource(bound, "candles:D")["rows"] == [
        {"t": 1720000000, "o": 10.0, "h": 12.0, "l": 9.0, "c": 11.125, "v": 1000.0},
    ]


@pytest.mark.asyncio
async def test_chart_fetch_rejection_does_not_read_source(tmp_path, isolated_web):
    orch, provider, _, request = setup_chart(tmp_path)
    provider.calls = [("web.fetch", {"url": SOURCE_URL})]

    async def reject(name, payload):
        if name == "approval.pending":
            orch.decide_approval(approval_id=payload["approval"]["approvalId"], decision="rejected")

    await collect(orch, request, reject)
    assert not isolated_web
    run = orch._run_store.get(request.session_key, request.idempotency_key)
    assert run.tool_steps[0]["policyDecision"] == "rejected_by_operator"


@pytest.mark.asyncio
async def test_chart_registry_enforces_web_scope_without_manifest_filter(tmp_path, isolated_web):
    orch, provider, store, request = setup_chart(tmp_path)
    bound = resolve_market_context(orch, request, request.idempotency_key)
    context = ToolExecutionContext(
        workdir=tmp_path, session_workspace_root=tmp_path, session_key=request.session_key,
        provider_name=provider.name, model=None, session_store=orch._session_store,
        transcript_store=orch._transcript_store, providers={},
        policy=chart_policy(policy_for_task_mode("full-access"), bound),
        market_context=bound, chart_store=store, run_id=bound.run_id, allowed_tool_ids=None,
    )
    for binding in (bound, replace(bound, access="read")):
        assert {"web.search", "web.fetch"} <= chart_tool_ids(binding)
        ctx = replace(context, market_context=binding)
        result = await orch._tool_registry.execute(
            ToolExecutionRequest(tool_id="web.search", arguments={"query": "TEST announcement"}), ctx)
        assert result.ok
        for tool_id in ("shell.exec", "files.read", "market.ticker", "memory.read", "market.forecast.read"):
            result = await orch._tool_registry.execute(ToolExecutionRequest(tool_id=tool_id, arguments={}), ctx)
            assert not result.ok and result.error == "tool outside bound scope"
    for lane in ("primary", None):
        forecast = replace(bound, forecast_id="synthetic-forecast", forecast_lane=lane)
        assert not {"web.search", "web.fetch"} & chart_tool_ids(forecast)
        for tool_id in ("web.search", "web.fetch", "market.chart.apply"):
            result = await orch._tool_registry.execute(
                ToolExecutionRequest(tool_id=tool_id, arguments={}), replace(context, market_context=forecast))
            assert not result.ok and result.error == "tool outside bound scope"
    assert len(isolated_web) == 2
    # Private fetches still fail before I/O even when a model invents the URL.
    result = await orch._tool_registry.execute(
        ToolExecutionRequest(tool_id="web.fetch", arguments={"url": "http://127.0.0.1/private"}), context)
    assert not result.ok and result.output["policyDecision"] == "egress_blocked"
