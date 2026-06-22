"""Memory RPC handlers."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from copenet.host.rpc_schema import EventFrame, ResponseFrame, RpcError, make_event_frame, make_response_frame
from copenet.prompts import list_profiles, list_task_modes


SendJson = Callable[[dict[str, Any]], Awaitable[None]]


async def handle_memory_list(request_id: str, params: dict[str, Any] | None, send_json: SendJson, orchestrator) -> None:
    raw = params or {}
    category = str(raw.get("category") or "").strip() or None
    limit = int(raw.get("limit") or 50)
    include_archived = bool(raw.get("includeArchived"))
    status = str(raw.get("status") or "active").strip().lower() or "active"
    await send_json(
        make_response_frame(
            ResponseFrame(
                id=request_id,
                ok=True,
                payload={
                    "items": orchestrator.list_memory(
                        include_archived=include_archived,
                        category=category,
                        status=status,
                        limit=limit,
                    )
                },
            )
        )
    )


async def handle_memory_upsert(
    request_id: str,
    params: dict[str, Any] | None,
    send_json: SendJson,
    orchestrator,
) -> None:
    raw = params or {}
    item = orchestrator.upsert_memory(
        memory_id=str(raw.get("id") or "").strip() or None,
        category=str(raw.get("category") or "").strip(),
        title=str(raw.get("title") or "").strip(),
        summary=str(raw.get("summary") or "").strip(),
        detail=str(raw.get("detail") or "").strip() or None,
        tags=[str(tag).strip() for tag in raw.get("tags")] if isinstance(raw.get("tags"), list) else [],
    )
    await send_json(
        make_response_frame(
            ResponseFrame(
                id=request_id,
                ok=True,
                payload={"memoryItem": item},
            )
        )
    )
    await send_json(make_event_frame(EventFrame(event="memory.changed", payload={"item": item, "reason": "upsert"})))


async def handle_memory_archive(
    request_id: str,
    params: dict[str, Any] | None,
    send_json: SendJson,
    orchestrator,
) -> None:
    raw = params or {}
    item = orchestrator.archive_memory(
        memory_id=str(raw.get("id") or "").strip(),
        archived=bool(raw.get("archived", True)),
    )
    await send_json(
        make_response_frame(
            ResponseFrame(
                id=request_id,
                ok=True,
                payload={"memoryItem": item},
            )
        )
    )
    if item is not None:
        await send_json(make_event_frame(EventFrame(event="memory.changed", payload={"item": item, "reason": "archive"})))


async def handle_memory_approve(
    request_id: str,
    params: dict[str, Any] | None,
    send_json: SendJson,
    orchestrator,
) -> None:
    raw = params or {}
    item = orchestrator.approve_memory(
        memory_id=str(raw.get("id") or "").strip(),
        category=str(raw.get("category") or "").strip() or None,
        title=raw.get("title") if raw.get("title") is None else str(raw.get("title")),
        summary=raw.get("summary") if raw.get("summary") is None else str(raw.get("summary")),
        detail=raw.get("detail") if raw.get("detail") is None else str(raw.get("detail")),
        tags=[str(tag).strip() for tag in raw.get("tags")] if isinstance(raw.get("tags"), list) else None,
    )
    await send_json(make_response_frame(ResponseFrame(id=request_id, ok=True, payload={"memoryItem": item})))
    if item is not None:
        await send_json(make_event_frame(EventFrame(event="memory.changed", payload={"item": item, "reason": "approved"})))


async def handle_memory_discard(
    request_id: str,
    params: dict[str, Any] | None,
    send_json: SendJson,
    orchestrator,
) -> None:
    raw = params or {}
    memory_id = str(raw.get("id") or "").strip()
    discarded = orchestrator.discard_memory(memory_id=memory_id)
    await send_json(make_response_frame(ResponseFrame(id=request_id, ok=True, payload={"discarded": discarded, "id": memory_id})))
    if discarded:
        await send_json(make_event_frame(EventFrame(event="memory.changed", payload={"id": memory_id, "reason": "discarded"})))
