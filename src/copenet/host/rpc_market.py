"""Market Monitor RPC handlers."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging
from typing import Any, Awaitable, Callable
from uuid import uuid4

from copenet.core.market import MarketRuntime
from copenet.core.market.backtester import run_portfolio_backtest, run_scenario
from copenet.core.market.edgar import fetch_fundamentals, fetch_ticker_evidence
from copenet.core.market.financials import (
    get_financial_series,
    supported_financial_metrics,
)
from copenet.core.market.ledger import resolve_due_claims
from copenet.core.market.ledger_report import ledger_report
from copenet.core.market.runtime import resolve_market_runtime
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


async def handle_market_chart_series_get(request_id: str, params: dict[str, Any] | None, send_json: SendJson, orchestrator) -> None:
    raw = params or {}
    symbols = raw.get("symbols")
    if not isinstance(symbols, list) or not all(isinstance(symbol, str) for symbol in symbols):
        raise ValueError("symbols must be a list of ticker strings")
    timeframe = raw.get("timeframe")
    if not isinstance(timeframe, str):
        raise ValueError("timeframe is required")
    payload = _runtime(orchestrator).chart_series(symbols, timeframe)
    await send_json(make_response_frame(ResponseFrame(id=request_id, ok=True, payload=payload.to_wire())))


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


async def handle_market_financial_metrics_list(request_id: str, params: dict[str, Any] | None, send_json: SendJson, orchestrator) -> None:
    """Every metric the overlay can request, so the UI never hardcodes the list."""
    del params, orchestrator
    await send_json(
        make_response_frame(
            ResponseFrame(
                id=request_id,
                ok=True,
                payload={"metrics": supported_financial_metrics()},
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
    raise ValueError("Choose a scan in Market → Scans & alerts, preview its scope, then Run now")


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
    payload: dict[str, Any] = {"target": target, "read": read}
    if target == "market":
        # Rides along with the read the briefing already polls rather than a second RPC — the
        # trail is only ever rendered beside the read it gives continuity to.
        payload["sessions"] = runtime.recent_sessions()
    await send_json(make_response_frame(ResponseFrame(id=request_id, ok=True, payload=payload)))


async def handle_market_brief_get(request_id: str, params: dict[str, Any] | None, send_json: SendJson, orchestrator) -> None:
    del params
    runtime = _runtime(orchestrator)
    await send_json(make_response_frame(ResponseFrame(id=request_id, ok=True, payload={"brief": runtime.store.load_morning_brief()})))


async def handle_market_brief_run(request_id: str, params: dict[str, Any] | None, send_json: SendJson, orchestrator) -> None:
    raise ValueError("Choose the morning scan in Market → Scans & alerts and preview its scope before running")


def _clamped_int(value: object, *, default: int, low: int, high: int) -> int:
    """Boundary coercion for an optional integer RPC param."""
    try:
        parsed = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    return max(low, min(high, parsed))


async def handle_market_ledger_get(request_id: str, params: dict[str, Any] | None, send_json: SendJson, orchestrator) -> None:
    """Forward-ledger calibration report. Resolves any past-due claims first so the page
    always shows current outcomes (resolution is cheap — stored bars, no network).
    `recent` bounds the claim list (default 30); the Ledger section asks for enough to show
    performance by week."""
    recent = _clamped_int((params or {}).get("recent"), default=30, low=1, high=1000)
    runtime = _runtime(orchestrator)
    try:
        await asyncio.to_thread(resolve_due_claims, runtime.store)
    except Exception:
        pass  # stale outcomes beat a failed page
    payload = await asyncio.to_thread(ledger_report, runtime.store, recent=recent)
    from copenet.core.orchestrator.market_forecasts import resolve_forecast_service
    from copenet.core.market.forecasts.ledger import ledger_forecasts
    service = resolve_forecast_service(orchestrator)
    payload["forecasts"] = await asyncio.to_thread(ledger_forecasts, service, params or {})
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
