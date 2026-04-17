"""RPC dispatch table for the CopeNet websocket host."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from copenet.host.rpc_schema import ResponseFrame, RpcError, make_response_frame

from .rpc_catalog import handle_models_list, handle_prompts_list, handle_providers_list, handle_tools_list
from .rpc_chat import handle_chat_abort, handle_chat_history, handle_chat_send
from .rpc_sessions import (
    handle_sessions_archive,
    handle_sessions_create,
    handle_sessions_debug_copy,
    handle_sessions_export,
    handle_sessions_list,
    handle_sessions_rename,
    handle_sessions_resolve,
)


SendJson = Callable[[dict[str, Any]], Awaitable[None]]


async def dispatch_rpc(req, send_json: SendJson, orchestrator, tasks: set) -> None:
    """Route one already-authenticated RPC request."""
    if req.method == "chat.send":
        await handle_chat_send(req.id, req.params, send_json, tasks, orchestrator)
    elif req.method == "chat.abort":
        await handle_chat_abort(req.id, req.params, send_json, orchestrator)
    elif req.method == "chat.history":
        await handle_chat_history(req.id, req.params, send_json, orchestrator)
    elif req.method == "sessions.list":
        await handle_sessions_list(req.id, req.params, send_json, orchestrator)
    elif req.method == "prompts.list":
        await handle_prompts_list(req.id, send_json)
    elif req.method == "providers.list":
        await handle_providers_list(req.id, send_json, orchestrator)
    elif req.method == "models.list":
        await handle_models_list(req.id, req.params, send_json, orchestrator)
    elif req.method == "tools.list":
        await handle_tools_list(req.id, send_json, orchestrator)
    elif req.method == "sessions.create":
        await handle_sessions_create(req.id, req.params, send_json, orchestrator)
    elif req.method == "sessions.rename":
        await handle_sessions_rename(req.id, req.params, send_json, orchestrator)
    elif req.method == "sessions.archive":
        await handle_sessions_archive(req.id, req.params, send_json, orchestrator)
    elif req.method == "sessions.debugCopy":
        await handle_sessions_debug_copy(req.id, req.params, send_json, orchestrator)
    elif req.method == "sessions.export":
        await handle_sessions_export(req.id, req.params, send_json, orchestrator)
    elif req.method == "sessions.resolve":
        await handle_sessions_resolve(req.id, req.params, send_json, orchestrator)
    else:
        await send_json(
            make_response_frame(
                ResponseFrame(
                    id=req.id,
                    ok=False,
                    error=RpcError(code="METHOD_NOT_FOUND", message=f"unknown method: {req.method}"),
                )
            )
        )
