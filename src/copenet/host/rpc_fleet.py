"""WebSocket RPC handlers for manual Fleet rooms."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable

from copenet.host.rpc_schema import EventFrame, ResponseFrame, make_event_frame, make_response_frame


SendJson = Callable[[dict[str, Any]], Awaitable[None]]
logger = logging.getLogger("copenet.fleet")


async def handle_fleet_list(request_id: str, params: dict[str, Any], send_json: SendJson, orchestrator) -> None:
    rooms = orchestrator._fleet.list_rooms(include_archived=bool(params.get("includeArchived")))
    await send_json(make_response_frame(ResponseFrame(id=request_id, ok=True, payload={"rooms": rooms})))


async def handle_fleet_get(request_id: str, params: dict[str, Any], send_json: SendJson, orchestrator) -> None:
    room_id = str(params.get("roomId") or "").strip()
    room = orchestrator._fleet.get_room(room_id)
    if room is None:
        raise ValueError(f"unknown Fleet room: {room_id}")
    await send_json(make_response_frame(ResponseFrame(id=request_id, ok=True, payload={"room": room})))


async def handle_fleet_create(request_id: str, params: dict[str, Any], send_json: SendJson, orchestrator) -> None:
    room = orchestrator._fleet.create_room(
        title=str(params.get("title") or "Fleet Room"),
        chatgpt_model=str(params.get("chatgptModel") or "").strip() or None,
        claude_model=str(params.get("claudeModel") or "").strip() or None,
        workspace_root=str(params.get("workspaceRoot") or "").strip() or None,
    )
    await send_json(make_response_frame(ResponseFrame(id=request_id, ok=True, payload={"room": room})))


async def handle_fleet_send(
    request_id: str,
    params: dict[str, Any],
    send_json: SendJson,
    tasks: set[asyncio.Task],
    orchestrator,
    broadcast: SendJson,
) -> None:
    room_id = str(params.get("roomId") or "").strip()
    target = str(params.get("target") or "@everyone").strip()
    message = str(params.get("message") or "").strip()
    if not room_id or not message:
        raise ValueError("roomId and message are required")
    orchestrator._fleet.validate_send(room_id=room_id, target=target, message=message)

    async def emit(event: dict[str, Any]) -> None:
        await broadcast(make_event_frame(EventFrame(event="fleet.event", payload={"roomId": room_id, "event": event})))

    async def run() -> None:
        await orchestrator._fleet.send_message(room_id=room_id, target=target, message=message, emit=emit)

    task = asyncio.create_task(run())
    tasks.add(task)

    def finish(completed: asyncio.Task) -> None:
        tasks.discard(completed)
        if completed.cancelled():
            return
        error = completed.exception()
        if error is not None:
            logger.error("Fleet room task failed for %s: %s", room_id, error)

    task.add_done_callback(finish)
    await send_json(
        make_response_frame(
            ResponseFrame(id=request_id, ok=True, payload={"roomId": room_id, "status": "accepted", "target": target})
        )
    )


async def handle_fleet_archive(request_id: str, params: dict[str, Any], send_json: SendJson, orchestrator) -> None:
    room_id = str(params.get("roomId") or "").strip()
    room = orchestrator._fleet.archive_room(room_id)
    await send_json(make_response_frame(ResponseFrame(id=request_id, ok=True, payload={"room": room})))
