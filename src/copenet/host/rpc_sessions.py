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
