"""Chat-style RPC handlers."""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable
from uuid import uuid4

from copenet.host.rpc_schema import ChatEventPayload, ResponseFrame, RpcError, make_chat_event, make_response_frame
from copenet.core.orchestrator import ChatSendRequest, SessionInFlightError
from copenet.prompts import compose_prompt


SendJson = Callable[[dict[str, Any]], Awaitable[None]]


async def handle_chat_send(
    request_id: str,
    params: dict[str, Any] | None,
    send_json: SendJson,
    tasks: set[asyncio.Task],
    orchestrator,
) -> None:
    raw = params or {}
    session_key = str(raw.get("sessionKey") or "").strip()
    message = str(raw.get("message") or "").strip()
    idempotency_key = str(raw.get("idempotencyKey") or "").strip()
    if not session_key or not message:
        await send_json(
            make_response_frame(
                ResponseFrame(
                    id=request_id,
                    ok=False,
                    error=RpcError(code="INVALID_REQUEST", message="sessionKey and message are required"),
                )
            )
        )
        return

    run_id = idempotency_key or str(uuid4())
    profile_id = str(raw.get("systemPromptId") or "").strip()
    task_prompt_id = str(raw.get("taskPromptId") or "").strip()
    system_prompt = compose_prompt(profile_id or None, task_prompt_id or None)

    await send_json(make_response_frame(ResponseFrame(id=request_id, ok=True, payload={"runId": run_id, "status": "started"})))

    async def emit_chat(payload: dict[str, Any]) -> None:
        await send_json(
            make_chat_event(
                ChatEventPayload(
                    run_id=str(payload.get("runId") or run_id),
                    session_key=str(payload.get("sessionKey") or session_key),
                    seq=int(payload.get("seq") or 0),
                    state=str(payload.get("state") or "error"),
                    message=payload.get("message") if isinstance(payload.get("message"), dict) else None,
                    error_message=str(payload.get("errorMessage")) if payload.get("errorMessage") else None,
                    provider=str(payload.get("provider")) if payload.get("provider") else None,
                    model=str(payload.get("model")) if payload.get("model") else None,
                    capabilities=payload.get("capabilities") if isinstance(payload.get("capabilities"), dict) else None,
                    tool_execution=payload.get("toolExecution") if isinstance(payload.get("toolExecution"), dict) else None,
                )
            )
        )

    async def run() -> None:
        try:
            await orchestrator.send_chat(
                ChatSendRequest(
                    session_key=session_key,
                    message=message,
                    idempotency_key=run_id,
                    provider=str(raw.get("provider") or "codex-cli"),
                    model=str(raw.get("model") or "").strip() or None,
                    system_prompt_id=profile_id or None,
                    task_prompt_id=task_prompt_id or None,
                    timeout_ms=int(raw.get("timeoutMs")) if raw.get("timeoutMs") else None,
                    system_prompt=system_prompt,
                ),
                emit=emit_chat,
            )
        except SessionInFlightError as exc:
            await send_json(
                make_response_frame(
                    ResponseFrame(
                        id=request_id,
                        ok=True,
                        payload={"runId": exc.run_id, "status": "in_flight"},
                    )
                )
            )
        except Exception as exc:
            await emit_chat(
                {
                    "runId": run_id,
                    "sessionKey": session_key,
                    "seq": 1,
                    "state": "error",
                    "errorMessage": str(exc),
                }
            )

    task = asyncio.create_task(run())
    tasks.add(task)
    task.add_done_callback(tasks.discard)


async def handle_chat_abort(request_id: str, params: dict[str, Any] | None, send_json: SendJson, orchestrator) -> None:
    raw = params or {}
    session_key = str(raw.get("sessionKey") or "").strip()
    run_id = str(raw.get("runId") or "").strip() or None
    if not session_key and not run_id:
        await send_json(
            make_response_frame(
                ResponseFrame(
                    id=request_id,
                    ok=False,
                    error=RpcError(code="INVALID_REQUEST", message="sessionKey or runId is required"),
                )
            )
        )
        return
    result = orchestrator.abort(session_key=session_key, run_id=run_id)
    await send_json(make_response_frame(ResponseFrame(id=request_id, ok=True, payload=result)))


async def handle_chat_history(request_id: str, params: dict[str, Any] | None, send_json: SendJson, orchestrator) -> None:
    raw = params or {}
    session_key = str(raw.get("sessionKey") or "").strip()
    limit = int(raw.get("limit") or 200)
    if not session_key:
        await send_json(
            make_response_frame(
                ResponseFrame(
                    id=request_id,
                    ok=False,
                    error=RpcError(code="INVALID_REQUEST", message="sessionKey is required"),
                )
            )
        )
        return
    messages = orchestrator.history(session_key=session_key, limit=limit)
    await send_json(
        make_response_frame(
            ResponseFrame(
                id=request_id,
                ok=True,
                payload={"sessionKey": session_key, "messages": messages},
            )
        )
    )
