"""Permissions RPC handlers — the global shell allowlist (Access & Permissions, Brick F).

Thin transport over the orchestrator's `*_shell_allowlist` methods, which own the
PermissionStore. Mirrors the CRUD shape of the messaging/memory handlers.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from copenet.host.rpc_schema import ResponseFrame, make_response_frame

SendJson = Callable[[dict[str, Any]], Awaitable[None]]


async def handle_permissions_allowlist_list(request_id: str, send_json: SendJson, orchestrator) -> None:
    await send_json(
        make_response_frame(
            ResponseFrame(id=request_id, ok=True, payload=orchestrator.list_shell_allowlist())
        )
    )


async def handle_permissions_allowlist_add(
    request_id: str,
    params: dict[str, Any] | None,
    send_json: SendJson,
    orchestrator,
) -> None:
    command = str((params or {}).get("command") or "").strip()
    payload = orchestrator.add_shell_allowlist(command)
    await send_json(make_response_frame(ResponseFrame(id=request_id, ok=True, payload=payload)))


async def handle_permissions_allowlist_remove(
    request_id: str,
    params: dict[str, Any] | None,
    send_json: SendJson,
    orchestrator,
) -> None:
    command = str((params or {}).get("command") or "").strip()
    payload = orchestrator.remove_shell_allowlist(command)
    await send_json(make_response_frame(ResponseFrame(id=request_id, ok=True, payload=payload)))
