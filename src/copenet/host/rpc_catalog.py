"""Catalog-style RPC handlers."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from copenet.host.rpc_schema import EventFrame, ResponseFrame, RpcError, make_event_frame, make_response_frame
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


async def handle_prompts_optimize(
    request_id: str,
    params: dict[str, Any] | None,
    send_json: SendJson,
    orchestrator,
) -> None:
    raw = params or {}
    prompt = str(raw.get("prompt") or "").strip()
    if not prompt:
        raise ValueError("prompt is required")
    payload = await orchestrator.optimize_prompt(
        prompt=prompt,
        provider_id=str(raw.get("provider") or "").strip() or None,
        model=str(raw.get("model") or "").strip() or None,
        custom_transform=str(raw.get("customTransform") or "").strip() or None,
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


async def handle_persona_get(request_id: str, params: dict[str, Any] | None, send_json: SendJson, orchestrator) -> None:
    raw = params or {}
    await send_json(
        make_response_frame(
            ResponseFrame(
                id=request_id,
                ok=True,
                payload={
                    "persona": orchestrator.get_persona(
                        provider=str(raw.get("provider") or "").strip() or None,
                        model=str(raw.get("model") or "").strip() or None,
                        privacy_tier=str(raw.get("privacyTier") or "").strip() or None,
                    )
                },
            )
        )
    )


async def handle_persona_settings_get(request_id: str, send_json: SendJson, orchestrator) -> None:
    await send_json(
        make_response_frame(
            ResponseFrame(
                id=request_id,
                ok=True,
                payload={"settings": orchestrator.get_persona_settings()},
            )
        )
    )


async def handle_persona_settings_update(
    request_id: str,
    params: dict[str, Any] | None,
    send_json: SendJson,
    orchestrator,
) -> None:
    raw = params or {}
    await send_json(
        make_response_frame(
            ResponseFrame(
                id=request_id,
                ok=True,
                payload={
                    "settings": orchestrator.update_persona_settings(
                        default_persona_id=str(raw.get("defaultPersonaId") or "").strip() or None,
                        default_privacy_tier=str(raw.get("defaultPrivacyTier") or "").strip() or None,
                        model_overrides=raw.get("modelOverrides") if isinstance(raw.get("modelOverrides"), dict) else None,
                    )
                },
            )
        )
    )


async def handle_persona_context_get(request_id: str, params: dict[str, Any] | None, send_json: SendJson, orchestrator) -> None:
    raw = params or {}
    await send_json(
        make_response_frame(
            ResponseFrame(
                id=request_id,
                ok=True,
                payload={
                    "personaContext": orchestrator.get_persona_context(
                        provider=str(raw.get("provider") or "").strip() or None,
                        model=str(raw.get("model") or "").strip() or None,
                        privacy_tier=str(raw.get("privacyTier") or "").strip() or None,
                        query=str(raw.get("query") or "").strip(),
                    )
                },
            )
        )
    )


async def handle_persona_read_file(request_id: str, params: dict[str, Any] | None, send_json: SendJson, orchestrator) -> None:
    raw = params or {}
    path = str(raw.get("path") or "").strip()
    if not path:
        await send_json(make_response_frame(ResponseFrame(id=request_id, ok=False, error=RpcError(code="INVALID_REQUEST", message="path is required"))))
        return
    try:
        result = orchestrator.read_persona_file(path=path)
    except (FileNotFoundError, ValueError) as exc:
        await send_json(make_response_frame(ResponseFrame(id=request_id, ok=False, error=RpcError(code="NOT_FOUND", message=str(exc) or "file not found"))))
        return
    await send_json(make_response_frame(ResponseFrame(id=request_id, ok=True, payload=result)))


async def handle_persona_write_file(request_id: str, params: dict[str, Any] | None, send_json: SendJson, orchestrator) -> None:
    raw = params or {}
    path = str(raw.get("path") or "").strip()
    content = raw.get("content")
    if not path or not isinstance(content, str):
        await send_json(make_response_frame(ResponseFrame(id=request_id, ok=False, error=RpcError(code="INVALID_REQUEST", message="path and string content are required"))))
        return
    try:
        result = orchestrator.write_persona_file(path=path, content=content)
    except (FileNotFoundError, ValueError) as exc:
        await send_json(make_response_frame(ResponseFrame(id=request_id, ok=False, error=RpcError(code="INVALID_REQUEST", message=str(exc) or "could not write file"))))
        return
    await send_json(make_response_frame(ResponseFrame(id=request_id, ok=True, payload=result)))


async def handle_persona_flavor_draft(
    request_id: str,
    params: dict[str, Any] | None,
    send_json: SendJson,
    orchestrator,
) -> None:
    raw = params or {}
    provider = str(raw.get("provider") or "").strip()
    if not provider:
        raise ValueError("provider is required")
    payload = await orchestrator.draft_persona_flavor(
        provider_id=provider,
        model=str(raw.get("model") or "").strip() or None,
    )
    await send_json(make_response_frame(ResponseFrame(id=request_id, ok=True, payload=payload)))


async def handle_persona_flavor_save(
    request_id: str,
    params: dict[str, Any] | None,
    send_json: SendJson,
    orchestrator,
) -> None:
    raw = params or {}
    provider = str(raw.get("provider") or "").strip()
    if not provider:
        raise ValueError("provider is required")
    draft = raw.get("draft") if isinstance(raw.get("draft"), dict) else {}
    await send_json(
        make_response_frame(
            ResponseFrame(
                id=request_id,
                ok=True,
                payload={
                    "flavor": orchestrator.save_persona_flavor(
                        provider_id=provider,
                        model=str(raw.get("model") or "").strip() or None,
                        draft=draft,
                    )
                },
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


async def handle_memory_list(request_id: str, params: dict[str, Any] | None, send_json: SendJson, orchestrator) -> None:
    raw = params or {}
    category = str(raw.get("category") or "").strip() or None
    limit = int(raw.get("limit") or 50)
    include_archived = bool(raw.get("includeArchived"))
    await send_json(
        make_response_frame(
            ResponseFrame(
                id=request_id,
                ok=True,
                payload={
                    "items": orchestrator.list_memory(
                        include_archived=include_archived,
                        category=category,
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
