"""Market Monitor read tools — let a chat session reason over the live dashboard.

Both tools are thin wrappers over :class:`MarketRuntime`, the same backend the
Market Monitor UI calls through ``rpc_market.py``. They read the persisted
dashboard/store state (``market.dashboard``) or run a live per-symbol lookup
(``market.ticker``) — no writes, no trading, no account mutation.
"""

from __future__ import annotations

from copenet.core.market.runtime import MarketRuntime
from copenet.core.tools.contracts import (
    ToolDescriptor,
    ToolExecutionContext,
    ToolExecutionRequest,
    ToolExecutionResult,
)


async def get_market_dashboard(request: ToolExecutionRequest, context: ToolExecutionContext) -> ToolExecutionResult:
    del context
    runtime = MarketRuntime()
    wire = runtime.dashboard().to_wire()
    regime = ((wire.get("regime") or {}).get("data") or {}).get("current")
    summary = f"Market dashboard — regime: {regime}" if regime else "Market dashboard loaded"
    return ToolExecutionResult(tool_id=request.tool_id, ok=True, summary=summary, output=wire)


async def get_market_ticker(request: ToolExecutionRequest, context: ToolExecutionContext) -> ToolExecutionResult:
    del context
    symbol = str(request.arguments.get("symbol") or "").strip()
    if not symbol:
        raise ValueError("symbol is required")
    runtime = MarketRuntime()
    detail = runtime.ticker(symbol)
    wire = detail.to_wire()
    summary = f"{detail.symbol}: {detail.last} ({detail.change})"
    return ToolExecutionResult(tool_id=request.tool_id, ok=True, summary=summary, output=wire)


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
            "Look up one symbol: price, daily/weekly/monthly bars, trend signals (RSI, drawdown, "
            "relative strength, benchmark verdict vs VOO/XLK), soft-bottoming insight, and related "
            "evidence. Runs a live data fetch, so prefer this over guessing when a question is about a "
            "specific ticker."
        ),
        category="context",
        input_schema={
            "type": "object",
            "properties": {"symbol": {"type": "string", "description": "Ticker symbol, e.g. 'XLK' or 'SOFI'."}},
            "required": ["symbol"],
            "additionalProperties": False,
        },
        capabilities=["market-data"],
        evidence_role="grounding",
        side_effect="read",
    ),
]

HANDLERS = {"market.dashboard": get_market_dashboard, "market.ticker": get_market_ticker}
