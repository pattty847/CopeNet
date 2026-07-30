"""Market Monitor RPC handlers."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable
from uuid import uuid4

from copenet.core.market import MarketRuntime
from copenet.core.market.backtester import run_portfolio_backtest, run_scenario
from copenet.core.market.edgar import fetch_fundamentals, fetch_ticker_evidence
from copenet.core.market.financials import get_financial_series
from copenet.core.market.ledger import ledger_report, resolve_due_claims
from copenet.core.market.runtime import resolve_market_runtime
from copenet.core.market.sentinel import run_morning_sweep
from copenet.core.runtime.runs import RunRecord
from copenet.host.rpc_schema import ResponseFrame, make_response_frame


SendJson = Callable[[dict[str, Any]], Awaitable[None]]


async def handle_market_dashboard_get(request_id: str, params: dict[str, Any] | None, send_json: SendJson, orchestrator) -> None:
    del params
    runtime = _runtime(orchestrator)
    await send_json(make_response_frame(ResponseFrame(id=request_id, ok=True, payload=runtime.dashboard().to_wire())))


async def handle_market_ticker_get(request_id: str, params: dict[str, Any] | None, send_json: SendJson, orchestrator) -> None:
    raw = params or {}
    symbol = str(raw.get("symbol") or "").strip()
    if not symbol:
        raise ValueError("symbol is required")
    runtime = _runtime(orchestrator)
    await send_json(make_response_frame(ResponseFrame(id=request_id, ok=True, payload=runtime.ticker(symbol).to_wire())))


async def handle_market_ticker_evidence_get(request_id: str, params: dict[str, Any] | None, send_json: SendJson, orchestrator) -> None:
    del orchestrator
    raw = params or {}
    symbol = str(raw.get("symbol") or "").strip().upper()
    if not symbol:
        raise ValueError("symbol is required")
    refresh = bool(raw.get("refresh"))
    try:
        days_back = int(raw.get("daysBack") or 180)
    except (TypeError, ValueError):
        days_back = 180
    payload = await fetch_ticker_evidence(symbol, refresh=refresh, days_back=days_back)
    await send_json(make_response_frame(ResponseFrame(id=request_id, ok=True, payload=payload.to_wire())))


async def handle_market_ticker_fundamentals_get(request_id: str, params: dict[str, Any] | None, send_json: SendJson, orchestrator) -> None:
    """Quarterly revenue/EPS series for the chart overlay. Lazy — the frontend only asks
    when the operator toggles the overlay on. `fundamentals` is null for ETFs/no-match filers."""
    del orchestrator
    raw = params or {}
    symbol = str(raw.get("symbol") or "").strip().upper()
    if not symbol:
        raise ValueError("symbol is required")
    fundamentals = await fetch_fundamentals(symbol, periods=12)
    await send_json(make_response_frame(ResponseFrame(id=request_id, ok=True, payload={"symbol": symbol, "fundamentals": fundamentals})))


async def handle_market_financial_series_get(request_id: str, params: dict[str, Any] | None, send_json: SendJson, orchestrator) -> None:
    """Canonical point-in-time financial observations shared with agent tools."""
    del orchestrator
    raw = params or {}
    symbol = str(raw.get("symbol") or "").strip().upper()
    if not symbol:
        raise ValueError("symbol is required")
    payload = await get_financial_series(
        symbol=symbol,
        metric=str(raw.get("metric") or "revenue"),
        frequency=str(raw.get("frequency") or "quarterly"),
        basis=str(raw.get("basis") or "canonical"),
        alignment=str(raw.get("alignment") or "availability"),
        as_of=_optional_text(raw.get("asOf")),
        start=_optional_text(raw.get("start")),
        end=_optional_text(raw.get("end")),
        refresh=bool(raw.get("refresh")),
        include_provenance=raw.get("includeProvenance") is not False,
    )
    await send_json(
        make_response_frame(
            ResponseFrame(
                id=request_id,
                ok=True,
                payload={"symbol": symbol, "series": payload},
            )
        )
    )


def _optional_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


async def handle_market_universe_get(request_id: str, params: dict[str, Any] | None, send_json: SendJson, orchestrator) -> None:
    del params
    runtime = _runtime(orchestrator)
    await send_json(make_response_frame(ResponseFrame(id=request_id, ok=True, payload=runtime.universe())))


async def handle_market_refresh(request_id: str, params: dict[str, Any] | None, send_json: SendJson, orchestrator) -> None:
    raw = params or {}
    scope = str(raw.get("scope") or "all").strip() or "all"
    if scope not in {"all", "macro", "signals", "edgar"}:
        raise ValueError("scope must be one of: all, macro, signals, edgar")
    runtime = _runtime(orchestrator)
    started_at = _now_iso()
    run_id = f"market-refresh-{uuid4().hex[:12]}"
    provider = _interpret_provider(orchestrator)

    async def _refresh_then_interpret() -> None:
        await asyncio.to_thread(runtime.refresh, scope=scope)
        # Default lane: one automatic whole-market model read per refresh (operator design).
        if provider is not None and scope in {"all", "signals"}:
            try:
                await runtime.interpret(provider, target="market")
            except Exception:
                pass  # the deterministic briefing still stands; the read stays stale

    _track_task(orchestrator, asyncio.create_task(_refresh_then_interpret()))
    await send_json(make_response_frame(ResponseFrame(id=request_id, ok=True, payload={"startedAt": started_at, "runId": run_id})))


async def handle_market_interpret(request_id: str, params: dict[str, Any] | None, send_json: SendJson, orchestrator) -> None:
    raw = params or {}
    target = str(raw.get("target") or "market").strip() or "market"
    runtime = _runtime(orchestrator)
    provider = _interpret_provider(orchestrator)
    if provider is None:
        raise ValueError("openai-codex provider unavailable — model reads need it configured")
    started_at = _now_iso()
    run_id = f"market-interpret-{uuid4().hex[:12]}"
    _track_task(orchestrator, asyncio.create_task(runtime.interpret(provider, target=target)))
    await send_json(
        make_response_frame(
            ResponseFrame(id=request_id, ok=True, payload={"startedAt": started_at, "runId": run_id, "target": target})
        )
    )


async def handle_market_read_get(request_id: str, params: dict[str, Any] | None, send_json: SendJson, orchestrator) -> None:
    raw = params or {}
    target = str(raw.get("target") or "market").strip() or "market"
    runtime = _runtime(orchestrator)
    read = runtime.store.load_market_read() if target == "market" else runtime.store.load_ticker_read(target)
    await send_json(make_response_frame(ResponseFrame(id=request_id, ok=True, payload={"target": target, "read": read})))


async def handle_market_brief_get(request_id: str, params: dict[str, Any] | None, send_json: SendJson, orchestrator) -> None:
    del params
    runtime = _runtime(orchestrator)
    await send_json(make_response_frame(ResponseFrame(id=request_id, ok=True, payload={"brief": runtime.store.load_morning_brief()})))


async def handle_market_brief_run(request_id: str, params: dict[str, Any] | None, send_json: SendJson, orchestrator) -> None:
    """Kick a morning sweep now (background). The operator asked, so force a regenerate even
    if today's brief already exists — same semantics as the Refresh button."""
    raw = params or {}
    force = raw.get("force") is not False
    runtime = _runtime(orchestrator)
    provider = _interpret_provider(orchestrator)
    pulse_store = getattr(orchestrator, "_pulse_store", None)
    _track_task(orchestrator, asyncio.create_task(run_morning_sweep(runtime, provider, pulse_store, force=force)))
    await send_json(make_response_frame(ResponseFrame(id=request_id, ok=True, payload={"startedAt": _now_iso()})))


async def handle_market_ledger_get(request_id: str, params: dict[str, Any] | None, send_json: SendJson, orchestrator) -> None:
    """Forward-ledger calibration report. Resolves any past-due claims first so the page
    always shows current outcomes (resolution is cheap — stored bars, no network)."""
    del params
    runtime = _runtime(orchestrator)
    try:
        await asyncio.to_thread(resolve_due_claims, runtime.store)
    except Exception:
        pass  # stale outcomes beat a failed page
    payload = await asyncio.to_thread(ledger_report, runtime.store)
    await send_json(make_response_frame(ResponseFrame(id=request_id, ok=True, payload=payload)))


def _interpret_provider(orchestrator):
    providers = getattr(orchestrator, "_providers", None)
    if isinstance(providers, dict):
        return providers.get("openai-codex")
    return None


def _track_task(orchestrator, task: asyncio.Task) -> None:
    background_tasks = getattr(orchestrator, "_background_tasks", None)
    if isinstance(background_tasks, set):
        background_tasks.add(task)
        task.add_done_callback(background_tasks.discard)


def _runtime(orchestrator) -> MarketRuntime:
    return resolve_market_runtime(orchestrator)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


async def handle_market_backtest_run(request_id: str, params: dict[str, Any] | None, send_json: SendJson, orchestrator) -> None:
    raw = params or {}
    session_key = str(raw.get("sessionKey") or "").strip()
    symbols = [str(s).strip().upper() for s in raw.get("symbols") or [] if str(s).strip()]
    weights = [float(w) for w in raw.get("weights") or []]
    start_date = str(raw.get("startDate") or "").strip()
    end_date = str(raw.get("endDate") or "").strip()
    benchmark = str(raw.get("benchmark") or "VOO").strip().upper()
    rebalance = str(raw.get("rebalance") or "buy_and_hold").strip()
    rebalance_interval = raw.get("rebalanceInterval")
    if rebalance_interval:
        rebalance_interval = str(rebalance_interval).strip()

    if not symbols:
        raise ValueError("symbols are required")
    if not weights:
        raise ValueError("weights are required")
    if not start_date or not end_date:
        raise ValueError("startDate and endDate are required")

    runtime = _runtime(orchestrator)
    result = await asyncio.to_thread(
        run_portfolio_backtest,
        symbols=symbols,
        weights=weights,
        start_date=start_date,
        end_date=end_date,
        benchmark=benchmark,
        rebalance=rebalance,
        rebalance_interval=rebalance_interval,
        store=runtime.store,
    )

    if session_key:
        run_id = f"backtest-{uuid4().hex[:12]}"
        now = _now_iso()

        run_record = RunRecord(
            run_id=run_id,
            session_key=session_key,
            provider="backtest-engine",
            model="v1-scoped",
            status="ok",
            user_message=f"Backtest: {', '.join(symbols)} vs {benchmark}",
            tool_execution_mode="guarded",
            will_attempt_tool_loop=False,
            started_at=now,
            completed_at=now,
            working_set={},
            message_count=0,
            input_token_estimate=0,
            tool_steps=[],
            artifact_ids=[],
            output_summary=f"Portfolio Return: {result.metrics['total_return']}%, Max Drawdown: {result.metrics['max_drawdown']}%",
            error=None,
            transition_reason=None,
            terminal_reason=None,
            tool_results=[],
            pending_input_count=0,
            oversized_tool_artifact_ids=[],
            metadata={"type": "backtest", "symbols": symbols, "weights": weights, "metrics": result.metrics},
        )
        orchestrator._run_store.create(run_record)

        body_md = f"""### Backtest Results

- **Symbols**: {", ".join(f"{s} ({w * 100:.1f}%)" for s, w in zip(symbols, weights))}
- **Date Range**: {start_date} to {end_date}
- **Rebalance Mode**: {rebalance} {f'({rebalance_interval})' if rebalance == 'periodic' else ''}
- **Benchmark**: {benchmark}

| Metric | Portfolio | Benchmark (VOO) |
|---|---|---|
| **Total Return** | {result.metrics['total_return']}% | {result.metrics['total_return'] - result.metrics['benchmark_total_return']}% |
| **Max Drawdown** | {result.metrics['max_drawdown']}% | {result.metrics['benchmark_max_drawdown']}% |
| **Sharpe Ratio** | {result.metrics['sharpe']} | {result.metrics['benchmark_sharpe']} |
| **Annualized Volatility** | {result.metrics['volatility']}% | {result.metrics['benchmark_volatility']}% |
| **Beta vs Benchmark** | {result.metrics['beta']} | 1.00 |
| **Correlation** | {result.metrics['correlation']} | 1.00 |
"""
        artifact = orchestrator._artifact_store.create(
            session_key=session_key,
            run_id=run_id,
            artifact_type="backtest",
            title=f"Backtest: {', '.join(symbols)}",
            body=body_md,
            metadata=result.to_json(),
        )
        run_record.artifact_ids.append(artifact.artifact_id)

    await send_json(make_response_frame(ResponseFrame(id=request_id, ok=True, payload=result.to_json())))


async def handle_market_backtest_stress_test(request_id: str, params: dict[str, Any] | None, send_json: SendJson, orchestrator) -> None:
    raw = params or {}
    session_key = str(raw.get("sessionKey") or "").strip()
    scenario_key = str(raw.get("scenarioKey") or "").strip()
    positions = raw.get("positions") or []

    if not scenario_key:
        raise ValueError("scenarioKey is required")

    result = await asyncio.to_thread(
        run_scenario,
        positions=positions,
        scenario_key=scenario_key,
    )

    if session_key:
        run_id = f"stress-test-{uuid4().hex[:12]}"
        now = _now_iso()

        run_record = RunRecord(
            run_id=run_id,
            session_key=session_key,
            provider="backtest-engine",
            model="v1-scoped",
            status="ok",
            user_message=f"Stress Test: {scenario_key}",
            tool_execution_mode="guarded",
            will_attempt_tool_loop=False,
            started_at=now,
            completed_at=now,
            working_set={},
            message_count=0,
            input_token_estimate=0,
            tool_steps=[],
            artifact_ids=[],
            output_summary=f"Projected Return: {result.metrics['total_return']}%, Max Drawdown: {result.metrics['max_drawdown']}%",
            error=None,
            transition_reason=None,
            terminal_reason=None,
            tool_results=[],
            pending_input_count=0,
            oversized_tool_artifact_ids=[],
            metadata={"type": "stress_test", "scenarioKey": scenario_key, "metrics": result.metrics},
        )
        orchestrator._run_store.create(run_record)

        body_md = f"""### Stress Test: {result.metadata['scenarioName']}

- **Duration**: {result.metadata['durationWeeks']} weeks
- **Simulated Impact**:

| Metric | Portfolio | Benchmark (VOO) |
|---|---|---|
| **Projected Return** | {result.metrics['total_return']}% | {result.metrics['total_return'] - result.metrics['benchmark_total_return']}% |
| **Max Drawdown** | {result.metrics['max_drawdown']}% | {result.metrics['benchmark_max_drawdown']}% |
| **Annualized Volatility** | {result.metrics['volatility']}% | {result.metrics['benchmark_volatility']}% |
| **Sharpe Ratio** | {result.metrics['sharpe']} | {result.metrics['benchmark_sharpe']} |
"""
        artifact = orchestrator._artifact_store.create(
            session_key=session_key,
            run_id=run_id,
            artifact_type="backtest",
            title=f"Stress Test: {result.metadata['scenarioName']}",
            body=body_md,
            metadata=result.to_json(),
        )
        run_record.artifact_ids.append(artifact.artifact_id)

    await send_json(make_response_frame(ResponseFrame(id=request_id, ok=True, payload=result.to_json())))
