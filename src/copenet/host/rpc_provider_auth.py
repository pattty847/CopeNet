"""Provider auth RPC handlers."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from copenet.host.rpc_schema import EventFrame, ResponseFrame, RpcError, make_event_frame, make_response_frame
from copenet.prompts import list_profiles, list_task_modes


SendJson = Callable[[dict[str, Any]], Awaitable[None]]


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
