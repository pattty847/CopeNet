"""Profile and briefing RPC handlers."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from copenet.host.rpc_schema import EventFrame, ResponseFrame, RpcError, make_event_frame, make_response_frame
from copenet.prompts import list_profiles, list_task_modes


SendJson = Callable[[dict[str, Any]], Awaitable[None]]


async def handle_profile_get(request_id: str, send_json: SendJson, orchestrator) -> None:
    await send_json(
        make_response_frame(
            ResponseFrame(
                id=request_id,
                ok=True,
                payload={"profile": orchestrator.get_pat_profile()},
            )
        )
    )


async def handle_identity_context_get(request_id: str, send_json: SendJson, orchestrator) -> None:
    await send_json(
        make_response_frame(
            ResponseFrame(
                id=request_id,
                ok=True,
                payload={"identityContext": orchestrator.get_identity_prompt_payload()},
            )
        )
    )


async def handle_profile_changelog(request_id: str, params: dict[str, Any] | None, send_json: SendJson, orchestrator) -> None:
    limit = int((params or {}).get("limit") or 20)
    await send_json(
        make_response_frame(
            ResponseFrame(
                id=request_id,
                ok=True,
                payload={"changelog": orchestrator.list_profile_changelog(limit=limit)},
            )
        )
    )


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
