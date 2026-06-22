"""Messaging RPC handlers."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from copenet.host.rpc_schema import EventFrame, ResponseFrame, RpcError, make_event_frame, make_response_frame
from copenet.prompts import list_profiles, list_task_modes


SendJson = Callable[[dict[str, Any]], Awaitable[None]]


async def handle_messaging_config_get(request_id: str, send_json: SendJson, orchestrator) -> None:
    await send_json(
        make_response_frame(
            ResponseFrame(
                id=request_id,
                ok=True,
                payload={"config": orchestrator.get_messaging_config()},
            )
        )
    )


async def handle_messaging_config_update(
    request_id: str,
    params: dict[str, Any] | None,
    send_json: SendJson,
    orchestrator,
) -> None:
    config = orchestrator.update_messaging_config(
        approval_policy=((params or {}).get("approvalPolicy") if isinstance((params or {}).get("approvalPolicy"), dict) else None),
        telegram_defaults=((params or {}).get("telegramDefaults") if isinstance((params or {}).get("telegramDefaults"), dict) else None),
    )
    await send_json(
        make_response_frame(
            ResponseFrame(
                id=request_id,
                ok=True,
                payload={"config": config},
            )
        )
    )
    await send_json(make_event_frame(EventFrame(event="messaging.updated", payload={"config": config})))


async def handle_messaging_test(
    request_id: str,
    params: dict[str, Any] | None,
    send_json: SendJson,
    orchestrator,
) -> None:
    platform = str((params or {}).get("platform") or "telegram").strip() or "telegram"
    payload = orchestrator.test_messaging_platform(platform)
    await send_json(
        make_response_frame(
            ResponseFrame(
                id=request_id,
                ok=True,
                payload=payload,
            )
        )
    )
    await send_json(make_event_frame(EventFrame(event="messaging.updated", payload={"config": payload["config"]})))


async def handle_messaging_destinations_list(request_id: str, send_json: SendJson, orchestrator) -> None:
    await send_json(
        make_response_frame(
            ResponseFrame(
                id=request_id,
                ok=True,
                payload={"destinations": orchestrator.list_messaging_destinations()},
            )
        )
    )


async def handle_messaging_destinations_upsert(
    request_id: str,
    params: dict[str, Any] | None,
    send_json: SendJson,
    orchestrator,
) -> None:
    payload = orchestrator.upsert_messaging_destination(
        destination=((params or {}).get("destination") if isinstance((params or {}).get("destination"), dict) else {}),
    )
    await send_json(
        make_response_frame(
            ResponseFrame(
                id=request_id,
                ok=True,
                payload=payload,
            )
        )
    )
    await send_json(make_event_frame(EventFrame(event="messaging.updated", payload={"config": payload["config"]})))


async def handle_messaging_destinations_delete(
    request_id: str,
    params: dict[str, Any] | None,
    send_json: SendJson,
    orchestrator,
) -> None:
    payload = orchestrator.delete_messaging_destination(destination_id=str((params or {}).get("destinationId") or ""))
    await send_json(
        make_response_frame(
            ResponseFrame(
                id=request_id,
                ok=True,
                payload=payload,
            )
        )
    )
    await send_json(make_event_frame(EventFrame(event="messaging.updated", payload={"config": payload["config"]})))


async def handle_messaging_routes_list(request_id: str, send_json: SendJson, orchestrator) -> None:
    await send_json(
        make_response_frame(
            ResponseFrame(
                id=request_id,
                ok=True,
                payload={"routes": orchestrator.list_messaging_routes()},
            )
        )
    )


async def handle_messaging_routes_upsert(
    request_id: str,
    params: dict[str, Any] | None,
    send_json: SendJson,
    orchestrator,
) -> None:
    payload = orchestrator.upsert_messaging_route(
        route=((params or {}).get("route") if isinstance((params or {}).get("route"), dict) else {}),
    )
    await send_json(
        make_response_frame(
            ResponseFrame(
                id=request_id,
                ok=True,
                payload=payload,
            )
        )
    )
    await send_json(make_event_frame(EventFrame(event="messaging.updated", payload={"routes": payload["routes"]})))


async def handle_messaging_routes_delete(
    request_id: str,
    params: dict[str, Any] | None,
    send_json: SendJson,
    orchestrator,
) -> None:
    payload = orchestrator.delete_messaging_route(route_id=str((params or {}).get("routeId") or ""))
    await send_json(
        make_response_frame(
            ResponseFrame(
                id=request_id,
                ok=True,
                payload=payload,
            )
        )
    )
    await send_json(make_event_frame(EventFrame(event="messaging.updated", payload={"routes": payload["routes"]})))


async def handle_messaging_routes_resolve(
    request_id: str,
    params: dict[str, Any] | None,
    send_json: SendJson,
    orchestrator,
) -> None:
    payload = orchestrator.resolve_messaging_route(
        platform=str((params or {}).get("platform") or "telegram"),
        chat_id=str((params or {}).get("chatId") or ""),
        thread_id=str((params or {}).get("threadId") or "").strip() or None,
        create_if_missing=bool((params or {}).get("createIfMissing", False)),
        title_hint=str((params or {}).get("titleHint") or "").strip() or None,
    )
    await send_json(
        make_response_frame(
            ResponseFrame(
                id=request_id,
                ok=True,
                payload=payload,
            )
        )
    )
