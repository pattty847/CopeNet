"""Return-briefing RPC handler."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from copenet.host.rpc_schema import ResponseFrame, make_response_frame


SendJson = Callable[[dict[str, Any]], Awaitable[None]]


async def handle_briefing_get(request_id: str, send_json: SendJson, orchestrator) -> None:
    await send_json(
        make_response_frame(
            ResponseFrame(
                id=request_id,
                ok=True,
                payload={"briefing": orchestrator.get_return_briefing()},
            )
        )
    )
