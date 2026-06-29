"""USER.md proposal RPC handlers (model-proposed identity deltas the operator reviews)."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from copenet.host.rpc_schema import EventFrame, ResponseFrame, make_event_frame, make_response_frame


SendJson = Callable[[dict[str, Any]], Awaitable[None]]


async def handle_user_notes_list(request_id: str, params: dict[str, Any] | None, send_json: SendJson, orchestrator) -> None:
    raw = params or {}
    status = str(raw.get("status") or "draft").strip().lower() or "draft"
    await send_json(
        make_response_frame(
            ResponseFrame(
                id=request_id,
                ok=True,
                payload={"items": orchestrator.list_user_notes(status=status)},
            )
        )
    )


async def handle_user_notes_approve(request_id: str, params: dict[str, Any] | None, send_json: SendJson, orchestrator) -> None:
    raw = params or {}
    item = orchestrator.approve_user_note(
        note_id=str(raw.get("id") or "").strip(),
        target_section=raw.get("targetSection") if raw.get("targetSection") is None else str(raw.get("targetSection")),
        summary=raw.get("summary") if raw.get("summary") is None else str(raw.get("summary")),
        body=raw.get("body") if raw.get("body") is None else str(raw.get("body")),
    )
    await send_json(make_response_frame(ResponseFrame(id=request_id, ok=True, payload={"userNote": item})))
    if item is not None:
        await send_json(make_event_frame(EventFrame(event="userNotes.changed", payload={"item": item, "reason": "approved"})))


async def handle_user_notes_discard(request_id: str, params: dict[str, Any] | None, send_json: SendJson, orchestrator) -> None:
    raw = params or {}
    note_id = str(raw.get("id") or "").strip()
    discarded = orchestrator.discard_user_note(note_id=note_id)
    await send_json(make_response_frame(ResponseFrame(id=request_id, ok=True, payload={"discarded": discarded, "id": note_id})))
    if discarded:
        await send_json(make_event_frame(EventFrame(event="userNotes.changed", payload={"id": note_id, "reason": "discarded"})))
