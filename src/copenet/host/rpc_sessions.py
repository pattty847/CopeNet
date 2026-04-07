"""Session-style RPC handlers."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from copenet.host.rpc_schema import ResponseFrame, RpcError, make_response_frame


SendJson = Callable[[dict[str, Any]], Awaitable[None]]


async def handle_sessions_list(request_id: str, params: dict[str, Any] | None, send_json: SendJson, orchestrator) -> None:
    include_archived = bool((params or {}).get("includeArchived", False))
    await send_json(
        make_response_frame(
            ResponseFrame(
                id=request_id,
                ok=True,
                payload={"sessions": orchestrator.list_sessions(include_archived=include_archived)},
            )
        )
    )


async def handle_sessions_create(request_id: str, params: dict[str, Any] | None, send_json: SendJson, orchestrator) -> None:
    raw = params or {}
    provider = str(raw.get("provider") or "").strip()
    model = str(raw.get("model") or "").strip() or None
    key = str(raw.get("key") or "").strip() or None
    title = str(raw.get("title") or "").strip() or None
    system_prompt_id = str(raw.get("systemPromptId") or "").strip() or None
    task_prompt_id = str(raw.get("taskPromptId") or "").strip() or None
    if not provider:
        await send_json(
            make_response_frame(
                ResponseFrame(
                    id=request_id,
                    ok=False,
                    error=RpcError(code="INVALID_REQUEST", message="provider is required"),
                )
            )
        )
        return
    try:
        session = orchestrator.create_session_with_profile(
            provider=provider,
            model=model,
            key=key,
            title=title,
            system_prompt_id=system_prompt_id,
            task_prompt_id=task_prompt_id,
        )
    except Exception as exc:
        await send_json(
            make_response_frame(
                ResponseFrame(
                    id=request_id,
                    ok=False,
                    error=RpcError(code="INVALID_REQUEST", message=str(exc)),
                )
            )
        )
        return
    await send_json(make_response_frame(ResponseFrame(id=request_id, ok=True, payload={"session": session})))


async def handle_sessions_rename(request_id: str, params: dict[str, Any] | None, send_json: SendJson, orchestrator) -> None:
    raw = params or {}
    key = str(raw.get("key") or "").strip()
    if not key:
        await send_json(
            make_response_frame(
                ResponseFrame(
                    id=request_id,
                    ok=False,
                    error=RpcError(code="INVALID_REQUEST", message="key is required"),
                )
            )
        )
        return
    try:
        session = orchestrator.rename_session(
            session_key=key,
            title=str(raw.get("title") or "").strip() or None,
        )
    except Exception as exc:
        await send_json(
            make_response_frame(
                ResponseFrame(
                    id=request_id,
                    ok=False,
                    error=RpcError(code="INVALID_REQUEST", message=str(exc)),
                )
            )
        )
        return
    await send_json(make_response_frame(ResponseFrame(id=request_id, ok=True, payload={"session": session})))


async def handle_sessions_archive(request_id: str, params: dict[str, Any] | None, send_json: SendJson, orchestrator) -> None:
    raw = params or {}
    key = str(raw.get("key") or "").strip()
    if not key:
        await send_json(
            make_response_frame(
                ResponseFrame(
                    id=request_id,
                    ok=False,
                    error=RpcError(code="INVALID_REQUEST", message="key is required"),
                )
            )
        )
        return
    try:
        session = orchestrator.archive_session(
            session_key=key,
            archived=bool(raw.get("archived", True)),
        )
    except Exception as exc:
        await send_json(
            make_response_frame(
                ResponseFrame(
                    id=request_id,
                    ok=False,
                    error=RpcError(code="INVALID_REQUEST", message=str(exc)),
                )
            )
        )
        return
    await send_json(make_response_frame(ResponseFrame(id=request_id, ok=True, payload={"session": session})))


async def handle_sessions_resolve(request_id: str, params: dict[str, Any] | None, send_json: SendJson, orchestrator) -> None:
    key = str((params or {}).get("key") or "").strip()
    if not key:
        await send_json(
            make_response_frame(
                ResponseFrame(
                    id=request_id,
                    ok=False,
                    error=RpcError(code="INVALID_REQUEST", message="key is required"),
                )
            )
        )
        return
    await send_json(
        make_response_frame(
            ResponseFrame(
                id=request_id,
                ok=True,
                payload={"session": orchestrator.resolve_session(key)},
            )
        )
    )
