"""Economic-calendar RPC handlers."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from copenet.core.market.economic_calendar import load_economic_calendar
from copenet.core.market.runtime import resolve_market_runtime
from copenet.host.rpc_schema import ResponseFrame, make_response_frame


SendJson = Callable[[dict[str, Any]], Awaitable[None]]


async def handle_market_calendar_get(request_id: str, params: dict[str, Any] | None, send_json: SendJson, orchestrator) -> None:
    raw = params or {}
    try:
        days = int(raw.get("days") or 7)
    except (TypeError, ValueError):
        days = 7
    runtime = resolve_market_runtime(orchestrator)
    payload = await load_economic_calendar(
        runtime.store.root_dir,
        days=days,
        refresh=bool(raw.get("refresh")),
    )
    await send_json(make_response_frame(ResponseFrame(id=request_id, ok=True, payload=payload)))
