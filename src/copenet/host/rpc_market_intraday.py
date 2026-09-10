"""Intraday bar RPC.

Its own module rather than another handler in `rpc_market.py`, which is already large and
covers a different lane: the daily/weekly/monthly series ship inside `ticker.detail` because
they all derive from one cached daily history, while intraday is a separate fetch per
interval and is requested only when an intraday timeframe is actually selected.
"""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable

from copenet.core.market.intraday import ALL_SESSIONS, EXTENDED, REGULAR, offerable_intervals
from copenet.core.market.runtime import resolve_market_runtime
from copenet.host.rpc_schema import ResponseFrame, RpcError, make_response_frame

SendJson = Callable[[dict[str, Any]], Awaitable[None]]

SESSIONS = (ALL_SESSIONS, REGULAR, EXTENDED)


async def handle_market_intraday_get(
    request_id: str, params: dict[str, Any] | None, send_json: SendJson, orchestrator
) -> None:
    raw = params or {}
    symbol = str(raw.get("symbol") or "").strip().upper()
    if not symbol:
        raise RpcError("symbol is required")

    interval = str(raw.get("interval") or "5m").strip()
    if interval not in offerable_intervals():
        raise RpcError(f"unsupported interval {interval!r} — offered: {', '.join(offerable_intervals())}")

    session = str(raw.get("session") or ALL_SESSIONS).strip()
    if session not in SESSIONS:
        raise RpcError(f"unknown session {session!r} — expected one of {', '.join(SESSIONS)}")

    days = raw.get("days")
    try:
        days = max(1, int(days)) if days is not None else None
    except (TypeError, ValueError):
        days = None

    runtime = resolve_market_runtime(orchestrator)
    # The fetch is blocking (yfinance is synchronous, and a paged 1m pull sleeps between
    # requests). Off the event loop, or one chart load stalls every other socket.
    series = await asyncio.to_thread(
        runtime.intraday.series,
        symbol, interval, session=session, days=days, refresh=bool(raw.get("refresh")),
    )
    await send_json(make_response_frame(ResponseFrame(id=request_id, ok=True, payload=series.to_wire())))


async def handle_market_intraday_intervals(
    request_id: str, params: dict[str, Any] | None, send_json: SendJson, orchestrator
) -> None:
    """What the selector may offer, with each interval's real depth.

    Sent rather than hardcoded in the client so the ceiling is visible at the point of
    choice. An operator picking `15m` should be able to see it reaches 60 days without
    discovering it as a chart that stops early.
    """
    del params, orchestrator
    from copenet.core.market.intraday import resolve

    await send_json(make_response_frame(ResponseFrame(id=request_id, ok=True, payload={
        "intervals": [
            {
                "interval": interval,
                "grain": (resolution := resolve(interval)).grain.key,
                "derived": resolution.derived,
                "windowDays": resolution.window_days,
                "paged": resolution.grain.paged,
            }
            for interval in offerable_intervals()
        ],
        "sessions": list(SESSIONS),
    })))


async def handle_market_ticker_profile_get(
    request_id: str, params: dict[str, Any] | None, send_json: SendJson, orchestrator
) -> None:
    """What this ticker IS — business, sector, website.

    Lazy, like the fundamentals overlay: the Overview tab asks when it renders, so opening a
    chart never waits on it. Cached for a month, because the answer does not change faster
    than that.
    """
    raw = params or {}
    symbol = str(raw.get("symbol") or "").strip().upper()
    if not symbol:
        raise RpcError("symbol is required")
    runtime = resolve_market_runtime(orchestrator)
    profile = await asyncio.to_thread(runtime.profiles.resolve, symbol, refresh=bool(raw.get("refresh")))
    await send_json(make_response_frame(ResponseFrame(id=request_id, ok=True, payload=profile.to_wire())))
