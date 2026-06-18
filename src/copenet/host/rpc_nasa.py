"""NASA Astronomy Picture of the Day RPC handlers.

`nasa.apod` fetches/serves today's (or a given date's) picture; `nasa.apod.list`
returns the collected days. Both return honest states so the UI never shows phantom
data: when `NASA_API_KEY` is unset, `configured` is false and `apod` is null; a fetch
failure surfaces as a non-null `error` string rather than a thrown RPC.
"""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable

from copenet.core.nasa import NasaApodError
from copenet.host.rpc_schema import ResponseFrame, make_response_frame


SendJson = Callable[[dict[str, Any]], Awaitable[None]]


async def handle_nasa_apod(request_id: str, params: dict[str, Any] | None, send_json: SendJson, orchestrator) -> None:
    raw = params or {}
    date = str(raw.get("date") or "").strip() or None
    refresh = bool(raw.get("refresh"))
    configured = orchestrator.nasa_configured

    apod: dict[str, Any] | None = None
    error: str | None = None
    if not configured:
        error = "NASA_API_KEY is not set"
    else:
        try:
            # Network + disk work — keep it off the event loop.
            apod = await asyncio.to_thread(orchestrator.fetch_apod, date=date, refresh=refresh)
        except NasaApodError as exc:
            error = str(exc)

    await send_json(
        make_response_frame(
            ResponseFrame(
                id=request_id,
                ok=True,
                payload={"configured": configured, "apod": apod, "error": error},
            )
        )
    )


async def handle_nasa_apod_list(request_id: str, params: dict[str, Any] | None, send_json: SendJson, orchestrator) -> None:
    raw = params or {}
    limit = int(raw.get("limit") or 60)
    await send_json(
        make_response_frame(
            ResponseFrame(
                id=request_id,
                ok=True,
                payload={"configured": orchestrator.nasa_configured, "apods": orchestrator.list_apods(limit=limit)},
            )
        )
    )
