"""Workspace file-viewer RPC handlers (read-only).

`workspace.listFiles` and `workspace.readFile` back the operator file viewer:
browse and render the files in a session's workspace root. Strictly read-only and
scoped to that root by the underlying workspace_files service.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from copenet.host.rpc_schema import ResponseFrame, RpcError, make_response_frame

SendJson = Callable[[dict[str, Any]], Awaitable[None]]


def _text(raw: dict[str, Any], key: str) -> str:
    value = raw.get(key)
    return str(value).strip() if value is not None else ""


async def _fail(request_id: str, message: str, send_json: SendJson) -> None:
    await send_json(
        make_response_frame(
            ResponseFrame(id=request_id, ok=False, error=RpcError(code="INVALID_REQUEST", message=message))
        )
    )


async def handle_workspace_list_files(request_id: str, params: dict[str, Any] | None, send_json: SendJson, orchestrator) -> None:
    raw = params or {}
    key = _text(raw, "key")
    if not key:
        await _fail(request_id, "key is required", send_json)
        return
    result = orchestrator.list_session_workspace_files(session_key=key)
    await send_json(make_response_frame(ResponseFrame(id=request_id, ok=True, payload=result)))


async def handle_workspace_read_file(request_id: str, params: dict[str, Any] | None, send_json: SendJson, orchestrator) -> None:
    raw = params or {}
    key = _text(raw, "key")
    path = _text(raw, "path")
    if not key or not path:
        await _fail(request_id, "key and path are required", send_json)
        return
    try:
        result = orchestrator.read_session_workspace_file(session_key=key, path=path)
    except (FileNotFoundError, ValueError) as exc:
        await send_json(
            make_response_frame(
                ResponseFrame(id=request_id, ok=False, error=RpcError(code="NOT_FOUND", message=str(exc) or "file not found"))
            )
        )
        return
    await send_json(make_response_frame(ResponseFrame(id=request_id, ok=True, payload=result)))
