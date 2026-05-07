"""Catalog-style RPC handlers."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from copenet.host.rpc_schema import EventFrame, ResponseFrame, make_event_frame, make_response_frame
from copenet.prompts import list_profiles, list_task_modes


SendJson = Callable[[dict[str, Any]], Awaitable[None]]


async def handle_prompts_list(request_id: str, send_json: SendJson) -> None:
    await send_json(
        make_response_frame(
            ResponseFrame(
                id=request_id,
                ok=True,
                payload={
                    "prompts": list_profiles(),
                    "profiles": list_profiles(),
                    "taskModes": list_task_modes(),
                },
            )
        )
    )


async def handle_providers_list(request_id: str, send_json: SendJson, orchestrator) -> None:
    await send_json(
        make_response_frame(
            ResponseFrame(
                id=request_id,
                ok=True,
                payload={"providers": await orchestrator.list_providers_catalog()},
            )
        )
    )


async def handle_models_list(request_id: str, params: dict[str, Any] | None, send_json: SendJson, orchestrator) -> None:
    provider_id = str((params or {}).get("provider") or "").strip() or None
    kind = str((params or {}).get("kind") or "chat").strip() or "chat"
    await send_json(
        make_response_frame(
            ResponseFrame(
                id=request_id,
                ok=True,
                payload={"models": await orchestrator.list_models(provider_id=provider_id, kind=kind)},
            )
        )
    )


async def handle_tools_list(request_id: str, send_json: SendJson, orchestrator) -> None:
    await send_json(
        make_response_frame(
            ResponseFrame(
                id=request_id,
                ok=True,
                payload={"tools": orchestrator.list_tools()},
            )
        )
    )


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


async def handle_runtime_context_get(request_id: str, send_json: SendJson, orchestrator) -> None:
    await send_json(
        make_response_frame(
            ResponseFrame(
                id=request_id,
                ok=True,
                payload={"runtimeContext": orchestrator.get_runtime_context()},
            )
        )
    )


async def handle_runtime_context_resolve(
    request_id: str,
    params: dict[str, Any] | None,
    send_json: SendJson,
    orchestrator,
) -> None:
    raw = params or {}
    session_key = str(raw.get("sessionKey") or "").strip() or None
    workspace_root = str(raw.get("workspaceRoot") or "").strip() or None
    await send_json(
        make_response_frame(
            ResponseFrame(
                id=request_id,
                ok=True,
                payload={"runtimeContext": orchestrator.get_runtime_context(session_key=session_key, workspace_root=workspace_root)},
            )
        )
    )


async def handle_runtime_workspace_browse(request_id: str, send_json: SendJson, orchestrator) -> None:
    selected = orchestrator.browse_workspace_root()
    await send_json(
        make_response_frame(
            ResponseFrame(
                id=request_id,
                ok=True,
                payload={
                    "workspaceRoot": selected,
                    "selected": bool(selected),
                    "runtimeContext": orchestrator.get_runtime_context(workspace_root=selected) if selected else None,
                },
            )
        )
    )


async def handle_runtime_workspace_set(
    request_id: str,
    params: dict[str, Any] | None,
    send_json: SendJson,
    orchestrator,
) -> None:
    workspace_root = orchestrator.validate_workspace_root(str((params or {}).get("workspaceRoot") or ""))
    await send_json(
        make_response_frame(
            ResponseFrame(
                id=request_id,
                ok=True,
                payload={
                    "workspaceRoot": workspace_root,
                    "runtimeContext": orchestrator.get_runtime_context(workspace_root=workspace_root),
                },
            )
        )
    )


async def handle_provider_auth_status(request_id: str, params: dict[str, Any] | None, send_json: SendJson, orchestrator) -> None:
    provider_id = str((params or {}).get("provider") or "").strip()
    if not provider_id:
        raise ValueError("provider is required")
    await send_json(
        make_response_frame(
            ResponseFrame(
                id=request_id,
                ok=True,
                payload={"status": orchestrator.provider_auth_status(provider_id)},
            )
        )
    )


async def handle_provider_auth_begin_login(request_id: str, params: dict[str, Any] | None, send_json: SendJson, orchestrator) -> None:
    provider_id = str((params or {}).get("provider") or "").strip()
    redirect_uri = str((params or {}).get("redirectUri") or "").strip() or None
    if not provider_id:
        raise ValueError("provider is required")
    await send_json(
        make_response_frame(
            ResponseFrame(
                id=request_id,
                ok=True,
                payload={"login": orchestrator.provider_auth_begin_login(provider_id, redirect_uri=redirect_uri)},
            )
        )
    )


async def handle_provider_auth_complete_login(request_id: str, params: dict[str, Any] | None, send_json: SendJson, orchestrator) -> None:
    provider_id = str((params or {}).get("provider") or "").strip()
    login_token = str((params or {}).get("loginToken") or "").strip()
    redirect_url = str((params or {}).get("redirectUrl") or "").strip() or None
    code = str((params or {}).get("code") or "").strip() or None
    state = str((params or {}).get("state") or "").strip() or None
    if not provider_id:
        raise ValueError("provider is required")
    if not login_token:
        raise ValueError("loginToken is required")
    await send_json(
        make_response_frame(
            ResponseFrame(
                id=request_id,
                ok=True,
                payload={
                    "status": orchestrator.provider_auth_complete_login(
                        provider_id,
                        login_token=login_token,
                        redirect_url=redirect_url,
                        code=code,
                        state=state,
                    )
                },
            )
        )
    )


async def handle_provider_auth_logout(request_id: str, params: dict[str, Any] | None, send_json: SendJson, orchestrator) -> None:
    provider_id = str((params or {}).get("provider") or "").strip()
    if not provider_id:
        raise ValueError("provider is required")
    await send_json(
        make_response_frame(
            ResponseFrame(
                id=request_id,
                ok=True,
                payload={"status": orchestrator.provider_auth_logout(provider_id)},
            )
        )
    )


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
