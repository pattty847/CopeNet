"""Persona RPC handlers."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from copenet.host.rpc_schema import EventFrame, ResponseFrame, RpcError, make_event_frame, make_response_frame
from copenet.prompts import list_profiles, list_task_modes


SendJson = Callable[[dict[str, Any]], Awaitable[None]]


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


async def handle_persona_list(request_id: str, params: dict[str, Any] | None, send_json: SendJson, orchestrator) -> None:
    raw = params or {}
    personas = orchestrator.list_personas(
        provider=str(raw.get("provider") or "").strip() or None,
        model=str(raw.get("model") or "").strip() or None,
    )
    await send_json(make_response_frame(ResponseFrame(id=request_id, ok=True, payload={"personas": personas})))


async def handle_persona_create(request_id: str, params: dict[str, Any] | None, send_json: SendJson, orchestrator) -> None:
    raw = params or {}
    persona_id = str(raw.get("personaId") or raw.get("id") or "").strip()
    display_name = str(raw.get("displayName") or "").strip() or None
    if not persona_id:
        await send_json(make_response_frame(ResponseFrame(id=request_id, ok=False, error=RpcError(code="INVALID_REQUEST", message="personaId is required"))))
        return
    try:
        result = orchestrator.create_persona(persona_id=persona_id, display_name=display_name)
    except ValueError as exc:
        await send_json(make_response_frame(ResponseFrame(id=request_id, ok=False, error=RpcError(code="INVALID_REQUEST", message=str(exc) or "could not create persona"))))
        return
    await send_json(make_response_frame(ResponseFrame(id=request_id, ok=True, payload={"persona": result})))


async def handle_persona_select(request_id: str, params: dict[str, Any] | None, send_json: SendJson, orchestrator) -> None:
    raw = params or {}
    persona_id = str(raw.get("personaId") or raw.get("id") or "").strip()
    if not persona_id:
        await send_json(make_response_frame(ResponseFrame(id=request_id, ok=False, error=RpcError(code="INVALID_REQUEST", message="personaId is required"))))
        return
    settings = orchestrator.select_persona(
        persona_id=persona_id,
        provider=str(raw.get("provider") or "").strip() or None,
        model=str(raw.get("model") or "").strip() or None,
    )
    await send_json(make_response_frame(ResponseFrame(id=request_id, ok=True, payload={"settings": settings})))


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
