"""Runtime context and workspace RPC handlers."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from copenet.host.rpc_schema import EventFrame, ResponseFrame, RpcError, make_event_frame, make_response_frame
from copenet.prompts import list_profiles, list_task_modes


SendJson = Callable[[dict[str, Any]], Awaitable[None]]


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
