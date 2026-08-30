"""Synthetic market formula chart RPC boundary."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from copenet.core.market.formulas import evaluate_formulas
from copenet.core.market.price_history import SPLIT_ADJUSTED
from copenet.core.market.runtime import CHART_BAR_LIMITS, resolve_market_runtime
from copenet.host.rpc_schema import ResponseFrame, make_response_frame


SendJson = Callable[[dict[str, Any]], Awaitable[None]]


async def handle_market_chart_formulas_get(
    request_id: str,
    params: dict[str, Any] | None,
    send_json: SendJson,
    orchestrator,
) -> None:
    raw = params or {}
    expressions = raw.get("expressions")
    if not isinstance(expressions, list) or not all(isinstance(item, str) for item in expressions):
        raise ValueError("expressions must be a list of formula strings")
    timeframe = raw.get("timeframe")
    if not isinstance(timeframe, str) or timeframe not in CHART_BAR_LIMITS:
        raise ValueError("timeframe must be daily, weekly, or monthly")
    runtime = resolve_market_runtime(orchestrator)
    formulas = evaluate_formulas(
        expressions,
        lambda symbol: runtime.cached_bars(symbol, timeframe, basis=SPLIT_ADJUSTED),
    )
    payload = {
        "timeframe": timeframe,
        "priceBasis": SPLIT_ADJUSTED,
        "formulas": [formula.to_wire() for formula in formulas],
    }
    await send_json(make_response_frame(ResponseFrame(id=request_id, ok=True, payload=payload)))
