"""Prompt, provider, model, and tool catalog RPC handlers."""

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
