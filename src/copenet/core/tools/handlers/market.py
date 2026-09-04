"""Market Monitor read tools — let a chat session reason over the live dashboard.

Both tools are thin wrappers over :class:`MarketRuntime`, the same backend the
Market Monitor UI calls through ``rpc_market.py``. They read the persisted
dashboard/store state (``market.dashboard``) or run a live per-symbol lookup
(``market.ticker``) — no writes, no trading, no account mutation.
"""

from __future__ import annotations

import asyncio
from typing import Any

from copenet.core.market.runtime import MarketRuntime
from copenet.core.tools.contracts import (
    ToolDescriptor,
    ToolExecutionContext,
    ToolExecutionRequest,
    ToolExecutionResult,
)

DEFAULT_BARS_LIMIT = 60
MAX_BARS_LIMIT = 500


async def get_market_dashboard(request: ToolExecutionRequest, context: ToolExecutionContext) -> ToolExecutionResult:
    del context
    runtime = MarketRuntime()
    wire = runtime.dashboard().to_wire()
    regime = ((wire.get("regime") or {}).get("data") or {}).get("current")
    summary = f"Market dashboard — regime: {regime}" if regime else "Market dashboard loaded"
    return ToolExecutionResult(tool_id=request.tool_id, ok=True, summary=summary, output=wire)


async def get_market_ticker(request: ToolExecutionRequest, context: ToolExecutionContext) -> ToolExecutionResult:
    symbol = str(request.arguments.get("symbol") or "").strip()
    if not symbol:
        raise ValueError("symbol is required")
    include_raw_bars = bool(request.arguments.get("includeRawBars"))
    bars_limit = int(request.arguments.get("bars") or DEFAULT_BARS_LIMIT)
    bars_limit = max(10, min(bars_limit, MAX_BARS_LIMIT))
    compare_arg = request.arguments.get("compareTo")
    compare_to = [str(item).strip() for item in compare_arg][:5] if isinstance(compare_arg, list) else None

    runtime = MarketRuntime()
    detail = runtime.ticker(symbol, compare=compare_to)
    wire = detail.to_wire()

    # The full series is what the Market Monitor UI charts from — the model doesn't need every
    # candle by default, just enough to eyeball recent structure. `includeRawBars` opts back in
    # for a genuine deep-history request (e.g. a backtest-style question).
    if not include_raw_bars:
        series = wire.get("series")
        if isinstance(series, dict):
            wire["series"] = {timeframe: bars[-bars_limit:] for timeframe, bars in series.items() if isinstance(bars, list)}

    thesis = _find_thesis(context, detail.symbol)
    if thesis is not None:
        wire.setdefault("intelligence", {})["thesis"] = thesis

    quote = detail.quote
    price = f"${quote.price:,.2f}" if quote.price is not None else "n/a"
    change = f"{quote.change_pct:+.2f}%" if quote.change_pct is not None else "n/a"
    summary = f"{detail.symbol}: {price} ({change} vs previous daily bar)"
    return ToolExecutionResult(tool_id=request.tool_id, ok=True, summary=summary, output=wire)


MAX_COMPARE_SYMBOLS = 8


async def compare_market_tickers(request: ToolExecutionRequest, context: ToolExecutionContext) -> ToolExecutionResult:
    del context
    symbols_arg = request.arguments.get("symbols")
    if not isinstance(symbols_arg, list) or len(symbols_arg) < 2:
        raise ValueError("symbols must be a list of at least 2 ticker symbols")
    symbols = [str(item).strip() for item in symbols_arg if str(item).strip()][:MAX_COMPARE_SYMBOLS]
    if len(symbols) < 2:
        raise ValueError("symbols must be a list of at least 2 ticker symbols")

    runtime = MarketRuntime()
    result = runtime.compare(symbols)
    wire = result.to_wire()
    summary = f"Compared {', '.join(row['symbol'] for row in wire.get('rows', []))}"
    return ToolExecutionResult(tool_id=request.tool_id, ok=True, summary=summary, output=wire)


def _find_thesis(context: ToolExecutionContext, symbol: str) -> dict[str, Any] | None:
    """Surface an existing market-thesis memory for this symbol, if the operator (or a prior model
    turn) has one on file, so the model can compare current data against the original reasoning."""
    service = getattr(context, "memory_service", None)
    if service is None:
        return None
    tag = f"symbol:{symbol}"
    rows = service.list_memory(category="market_thesis", limit=50)
    match = next((item for item in rows if tag in item.tags), None)
    if match is None:
        return None
    return {
        "title": match.title,
        "summary": match.summary,
        "detail": match.detail,
        "updatedAt": match.updated_at,
    }


DESCRIPTORS = [
    ToolDescriptor(
        id="market.dashboard",
        name="Get Market Dashboard",
        description=(
            "Read the current Market Monitor dashboard: sector rotation (RRG), macro board, "
            "accumulation/trend/soft-bottoming watchlists, portfolio, speculative positions, evidence, "
            "and the synthesized briefing + regime read. Use this before answering any question about "
            "current market conditions, sectors, or the operator's positions."
        ),
        category="context",
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        capabilities=["market-data"],
        evidence_role="grounding",
        side_effect="read",
    ),
    ToolDescriptor(
        id="market.ticker",
        name="Get Ticker Detail",
        description=(
            "Look up one symbol. Returns an `intelligence` packet with the numbers already computed by "
            "the Insight Engine — trend (MA stack, long-term trend), momentum (RSI, ATR, volume), "
            "returns (1w/4w/13w/26w/52w/YTD/3y), drawdown vs 52w and full-history highs, volatility "
            "and beta/correlation vs VOO, relative strength + benchmark verdicts, sector rotation (RRG) "
            "quadrant, the operator's position in this symbol if held, best-effort ETF top-holdings/"
            "sector-weight exposure when the symbol is a fund, and any saved market-thesis memory for "
            "this symbol so you can check current data against the original reasoning. `intelligence."
            "asOf` is the timestamp this data was fetched — treat anything you're told separately as "
            "possibly older than that. Benchmarks default to the broad market/growth read (VOO/XLK/QQQ) "
            "— pass `compareTo` with specific symbols (a sector ETF, a direct competitor) only when the "
            "question calls for it; the defaults are the right choice most of the time. For comparing "
            "two or more tickers head-to-head, use `market.compare` instead. Also returns daily/weekly/"
            "monthly OHLCV bars (trimmed to the last `bars` per timeframe by default — pass "
            "`includeRawBars: true` for the full multi-year series). Runs a live data fetch, so prefer "
            "this over guessing when a question is about a specific ticker."
        ),
        category="context",
        input_schema={
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Ticker symbol, e.g. 'XLK' or 'SOFI'."},
                "compareTo": {
                    "type": "array",
                    "items": {"type": "string"},
                    "maxItems": 5,
                    "description": "Extra symbols to benchmark against, added on top of the default VOO/XLK/QQQ set (e.g. a sector ETF or a direct competitor). Leave unset unless the question specifically calls for a different comparison.",
                },
                "includeRawBars": {
                    "type": "boolean",
                    "description": "Return the full OHLCV series per timeframe instead of the trimmed default. Only ask for this for a genuine deep-history question (e.g. backtesting).",
                },
                "bars": {
                    "type": "integer",
                    "minimum": 10,
                    "maximum": MAX_BARS_LIMIT,
                    "description": f"Bars per timeframe to keep when includeRawBars is false. Default {DEFAULT_BARS_LIMIT}.",
                },
            },
            "required": ["symbol"],
            "additionalProperties": False,
        },
        capabilities=["market-data"],
        evidence_role="grounding",
        side_effect="read",
    ),
    ToolDescriptor(
        id="market.compare",
        name="Compare Tickers",
        description=(
            "Compare two or more symbols side by side — any mix of stocks/ETFs, no primary/anchor "
            "symbol required. Returns each symbol's own price, returns (1w/4w/13w/26w/52w/YTD), 13w "
            "volatility, 52w drawdown, RSI-14, MA stack, and long-term trend, plus a simple rank by "
            "13w return. It deliberately does NOT compute a pairwise verdict or pick a winner — reason "
            "over the numbers yourself and say which one is actually better and why. Use this instead "
            "of calling market.ticker twice when the question is a head-to-head or a batch comparison."
        ),
        category="context",
        input_schema={
            "type": "object",
            "properties": {
                "symbols": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 2,
                    "maxItems": MAX_COMPARE_SYMBOLS,
                    "description": "Ticker symbols to compare, e.g. ['NVDA', 'AMD'] or a longer list.",
                },
            },
            "required": ["symbols"],
            "additionalProperties": False,
        },
        capabilities=["market-data"],
        evidence_role="grounding",
        side_effect="read",
    ),
    ToolDescriptor(
        id="market.backtest",
        name="Run Backtest or Stress Test",
        description=(
            "Run a portfolio historical backtest or a macro stress test scenario on current holdings. "
            "Supports: mode='backtest' with parameters symbols, weights, startDate, endDate, benchmark, "
            "rebalance ('buy_and_hold' or 'periodic'), and rebalanceInterval ('daily', 'weekly', 'monthly'). "
            "Or mode='stress_test' with scenarioName ('2022_tech_dump', '2020_covid_crash')."
        ),
        category="context",
        input_schema={
            "type": "object",
            "properties": {
                "mode": {"type": "string", "enum": ["backtest", "stress_test"], "description": "Mode to run: 'backtest' for portfolio backtesting, 'stress_test' for macro shock simulation."},
                "symbols": {"type": "array", "items": {"type": "string"}, "description": "Tickers to backtest. Required for mode='backtest'."},
                "weights": {"type": "array", "items": {"type": "number"}, "description": "Weights matching symbols. Required for mode='backtest'."},
                "startDate": {"type": "string", "description": "Start date (YYYY-MM-DD). Required for mode='backtest'."},
                "endDate": {"type": "string", "description": "End date (YYYY-MM-DD). Required for mode='backtest'."},
                "benchmark": {"type": "string", "description": "Benchmark ticker. Default 'VOO'."},
                "rebalance": {"type": "string", "enum": ["buy_and_hold", "periodic"], "description": "Rebalance mode. Default 'buy_and_hold'."},
                "rebalanceInterval": {"type": "string", "enum": ["daily", "weekly", "monthly"], "description": "Rebalance interval for periodic mode."},
                "scenarioName": {"type": "string", "enum": ["2022_tech_dump", "2020_covid_crash"], "description": "Scenario key to run. Required for mode='stress_test'."}
            },
            "required": ["mode"],
            "additionalProperties": False,
        },
        capabilities=["market-data"],
        evidence_role="grounding",
        side_effect="read",
    ),
]


async def run_market_backtest(request: ToolExecutionRequest, context: ToolExecutionContext) -> ToolExecutionResult:
    mode = str(request.arguments.get("mode") or "backtest").strip().lower()

    # Lazy import to avoid circular dependency
    from copenet.core.market.backtester import run_portfolio_backtest, run_scenario

    runtime = MarketRuntime()

    if mode == "stress_test":
        scenario_key = str(request.arguments.get("scenarioName") or "2022_tech_dump").strip()
        from copenet.core.market.universe import PORTFOLIO_BASIS
        positions = []
        if context.session_key:
            try:
                from copenet.core.market.webull.sync import load_snapshot
                snapshot = load_snapshot()
                if snapshot and snapshot.get("positions"):
                    for p in snapshot["positions"]:
                        positions.append({
                            "symbol": p["symbol"],
                            "shares": p["shares"],
                            "last": p["last"],
                        })
            except Exception:
                pass

        if not positions:
            for sym, data in PORTFOLIO_BASIS.items():
                positions.append({
                    "symbol": sym,
                    "shares": data["shares"],
                    "last": data["avg_cost"],
                })

        result = await asyncio.to_thread(
            run_scenario,
            positions=positions,
            scenario_key=scenario_key,
        )

        if context.session_key and context.artifact_store and context.run_id:
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
            context.artifact_store.create(
                session_key=context.session_key,
                run_id=context.run_id,
                artifact_type="backtest",
                title=f"Stress Test: {result.metadata['scenarioName']}",
                body=body_md,
                metadata=result.to_json(),
            )

        summary = f"Stress Test: {result.metadata['scenarioName']} completed. Projected Return: {result.metrics['total_return']}%"
        return ToolExecutionResult(tool_id=request.tool_id, ok=True, summary=summary, output=result.to_json())

    else:
        symbols = [str(s).strip().upper() for s in request.arguments.get("symbols") or [] if str(s).strip()]
        weights = [float(w) for w in request.arguments.get("weights") or []]
        start_date = str(request.arguments.get("startDate") or "").strip()
        end_date = str(request.arguments.get("endDate") or "").strip()
        benchmark = str(request.arguments.get("benchmark") or "VOO").strip().upper()
        rebalance = str(request.arguments.get("rebalance") or "buy_and_hold").strip()
        rebalance_interval = request.arguments.get("rebalanceInterval")
        if rebalance_interval:
            rebalance_interval = str(rebalance_interval).strip()

        if not symbols:
            raise ValueError("symbols are required")
        if not weights:
            raise ValueError("weights are required")
        if not start_date or not end_date:
            raise ValueError("startDate and endDate are required")

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

        if context.session_key and context.artifact_store and context.run_id:
            body_md = f"""### Backtest Results

- **Symbols**: {", ".join(f"{s} ({w * 100:.1f}%)" for s, w in zip(symbols, weights))}
- **Date Range**: {start_date} to {end_date}
- **Rebalance Mode**: {rebalance} {f'({rebalance_interval})' if rebalance == 'periodic' else ''}
- **Benchmark**: {benchmark}

| Metric | Portfolio | Benchmark (VOO) |
|---|---|---|
| **Total Return** | {result.metrics['total_return']}% | {result.metrics['benchmark_total_return'] + result.metrics['total_return']}% |
| **Max Drawdown** | {result.metrics['max_drawdown']}% | {result.metrics['benchmark_max_drawdown']}% |
| **Sharpe Ratio** | {result.metrics['sharpe']} | {result.metrics['benchmark_sharpe']} |
| **Annualized Volatility** | {result.metrics['volatility']}% | {result.metrics['benchmark_volatility']}% |
| **Beta vs Benchmark** | {result.metrics['beta']} | 1.00 |
| **Correlation** | {result.metrics['correlation']} | 1.00 |
"""
            context.artifact_store.create(
                session_key=context.session_key,
                run_id=context.run_id,
                artifact_type="backtest",
                title=f"Backtest: {', '.join(symbols)}",
                body=body_md,
                metadata=result.to_json(),
            )

        summary = f"Backtest: {', '.join(symbols)} vs {benchmark} completed. Portfolio Return: {result.metrics['total_return']}%"
        return ToolExecutionResult(tool_id=request.tool_id, ok=True, summary=summary, output=result.to_json())


HANDLERS = {
    "market.dashboard": get_market_dashboard,
    "market.ticker": get_market_ticker,
    "market.compare": compare_market_tickers,
    "market.backtest": run_market_backtest,
}

# Kept in a focused module so this already-large handler stays navigable while
# market.* continues to have one canonical registration point.
from .market_evidence import DESCRIPTORS as EVIDENCE_DESCRIPTORS, HANDLERS as EVIDENCE_HANDLERS  # noqa: E402
from .market_financials import DESCRIPTORS as FINANCIAL_DESCRIPTORS, HANDLERS as FINANCIAL_HANDLERS  # noqa: E402

from .market_chart import DESCRIPTORS as CHART_DESCRIPTORS, HANDLERS as CHART_HANDLERS  # noqa: E402

DESCRIPTORS += EVIDENCE_DESCRIPTORS + FINANCIAL_DESCRIPTORS + CHART_DESCRIPTORS
HANDLERS.update(CHART_HANDLERS)
HANDLERS.update(EVIDENCE_HANDLERS)
HANDLERS.update(FINANCIAL_HANDLERS)
