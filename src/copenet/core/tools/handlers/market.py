"""Market Monitor read tools — let a chat session reason over the live dashboard.

Both tools are thin wrappers over :class:`MarketRuntime`, the same backend the
Market Monitor UI calls through ``rpc_market.py``. They read the persisted
dashboard/store state (``market.dashboard``) or run a live per-symbol lookup
(``market.ticker``) — no writes, no trading, no account mutation.
"""

from __future__ import annotations

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

    runtime = MarketRuntime()
    detail = runtime.ticker(symbol)
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

    summary = f"{detail.symbol}: {detail.last} ({detail.change})"
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
            "and beta/correlation vs VOO, relative strength + benchmark verdicts (VOO/XLK/QQQ), sector "
            "rotation (RRG) quadrant, the operator's position in this symbol if held, best-effort ETF "
            "top-holdings/sector-weight exposure when the symbol is a fund, and any saved market-thesis "
            "memory for this symbol so you can check current data against the original reasoning. Also "
            "returns daily/weekly/monthly OHLCV bars (trimmed to the last `bars` per timeframe by "
            "default — pass `includeRawBars: true` for the full multi-year series). Runs a live data "
            "fetch, so prefer this over guessing when a question is about a specific ticker."
        ),
        category="context",
        input_schema={
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Ticker symbol, e.g. 'XLK' or 'SOFI'."},
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
]

HANDLERS = {"market.dashboard": get_market_dashboard, "market.ticker": get_market_ticker}
