"""Treasury yield-curve RPC handler."""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable

from copenet.core.market.yield_curve import YieldCurveRange, fetch_treasury_yield_curve
from copenet.host.rpc_schema import ResponseFrame, make_response_frame


SendJson = Callable[[dict[str, Any]], Awaitable[None]]
VALID_RANGES: set[str] = {"1d", "1w", "1m"}


async def handle_market_yield_curve_get(
    request_id: str,
    params: dict[str, Any] | None,
    send_json: SendJson,
    orchestrator,
) -> None:
    del orchestrator
    selected_range = str((params or {}).get("range") or "1d").lower()
    if selected_range not in VALID_RANGES:
        raise ValueError("range must be one of: 1d, 1w, 1m")
    payload = await asyncio.to_thread(
        fetch_treasury_yield_curve,
        selected_range,  # type: ignore[arg-type]
        refresh=bool((params or {}).get("refresh")),
    )
    await send_json(make_response_frame(ResponseFrame(id=request_id, ok=True, payload=payload)))
