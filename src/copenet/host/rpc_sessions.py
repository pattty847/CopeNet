"""Session-style RPC handlers."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from copenet.host.rpc_schema import ResponseFrame, RpcError, make_response_frame


SendJson = Callable[[dict[str, Any]], Awaitable[None]]


def _required_text(raw: dict[str, Any], key: str) -> str:
    value = raw.get(key)
    return str(value).strip() if value is not None else ""


def _optional_text(raw: dict[str, Any], key: str) -> str | None:
    value = raw.get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _string_list(raw: dict[str, Any], key: str) -> list[str]:
    value = raw.get(key)
    if not isinstance(value, list):
        return []
    rows: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text:
            rows.append(text)
    return rows


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
    provider = _required_text(raw, "provider")
    model = _optional_text(raw, "model")
    key = _optional_text(raw, "key")
    title = _optional_text(raw, "title")
    system_prompt_id = _optional_text(raw, "systemPromptId")
    task_prompt_id = _optional_text(raw, "taskPromptId")
    workspace_root = _optional_text(raw, "workspaceRoot")
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
            workspace_root=workspace_root,
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
    key = _required_text(raw, "key")
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
            title=_optional_text(raw, "title"),
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
    key = _required_text(raw, "key")
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
    key = _required_text(params or {}, "key")
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


async def handle_sessions_runs(request_id: str, params: dict[str, Any] | None, send_json: SendJson, orchestrator) -> None:
    raw = params or {}
    key = _required_text(raw, "key")
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
    limit = raw.get("limit", 50)
    try:
        parsed_limit = max(1, int(limit))
    except (TypeError, ValueError):
        parsed_limit = 50
    await send_json(
        make_response_frame(
            ResponseFrame(
                id=request_id,
                ok=True,
                payload={"runs": orchestrator.list_session_runs(key, limit=parsed_limit)},
            )
        )
    )


async def handle_sessions_run(request_id: str, params: dict[str, Any] | None, send_json: SendJson, orchestrator) -> None:
    raw = params or {}
    key = _required_text(raw, "key")
    run_id = _required_text(raw, "runId")
    if not key or not run_id:
        await send_json(
            make_response_frame(
                ResponseFrame(
                    id=request_id,
                    ok=False,
                    error=RpcError(code="INVALID_REQUEST", message="key and runId are required"),
                )
            )
        )
        return
    await send_json(
        make_response_frame(
            ResponseFrame(
                id=request_id,
                ok=True,
                payload={"run": orchestrator.resolve_session_run(key, run_id)},
            )
        )
    )


async def handle_sessions_state(request_id: str, params: dict[str, Any] | None, send_json: SendJson, orchestrator) -> None:
    raw = params or {}
    key = _required_text(raw, "key")
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
                payload={"state": orchestrator.resolve_session_state(key)},
            )
        )
    )


async def handle_sessions_artifacts(request_id: str, params: dict[str, Any] | None, send_json: SendJson, orchestrator) -> None:
    raw = params or {}
    key = _required_text(raw, "key")
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
    limit = raw.get("limit", 50)
    try:
        parsed_limit = max(1, int(limit))
    except (TypeError, ValueError):
        parsed_limit = 50
    await send_json(
        make_response_frame(
            ResponseFrame(
                id=request_id,
                ok=True,
                payload={"artifacts": orchestrator.list_session_artifacts(key, limit=parsed_limit)},
            )
        )
    )


async def handle_sessions_debug_copy(request_id: str, params: dict[str, Any] | None, send_json: SendJson, orchestrator) -> None:
    key = _required_text(params or {}, "key")
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
        session = orchestrator.debug_copy_session(key)
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


async def handle_sessions_export(request_id: str, params: dict[str, Any] | None, send_json: SendJson, orchestrator) -> None:
    key = _required_text(params or {}, "key")
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
        exported = orchestrator.export_session(key)
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
    await send_json(make_response_frame(ResponseFrame(id=request_id, ok=True, payload=exported)))


async def handle_sessions_merge_create(
    request_id: str,
    params: dict[str, Any] | None,
    send_json: SendJson,
    orchestrator,
) -> None:
    raw = params or {}
    source_session_keys = _string_list(raw, "sourceSessionKeys")
    provider = _required_text(raw, "provider")
    if len(source_session_keys) < 2:
        await send_json(
            make_response_frame(
                ResponseFrame(
                    id=request_id,
                    ok=False,
                    error=RpcError(code="INVALID_REQUEST", message="at least 2 sourceSessionKeys are required"),
                )
            )
        )
        return
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

    async def emit_side_event(event: str, payload: dict[str, Any]) -> None:
        await send_json({"type": "event", "event": event, "payload": payload})

    try:
        merged = await orchestrator.merge_sessions(
            source_session_keys=source_session_keys,
            provider=provider,
            model=_optional_text(raw, "model"),
            system_prompt_id=_optional_text(raw, "systemPromptId"),
            task_prompt_id=_optional_text(raw, "taskPromptId"),
            workspace_root=_optional_text(raw, "workspaceRoot"),
            title=_optional_text(raw, "title"),
            emit_event=emit_side_event,
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
    await send_json(make_response_frame(ResponseFrame(id=request_id, ok=True, payload=merged)))


async def handle_sessions_merge_state(request_id: str, params: dict[str, Any] | None, send_json: SendJson, orchestrator) -> None:
    key = _required_text(params or {}, "key")
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
                payload={"mergeState": orchestrator.resolve_merge_state(key)},
            )
        )
    )
