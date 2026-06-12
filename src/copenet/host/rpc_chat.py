"""Chat-style RPC handlers."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Awaitable, Callable
from uuid import uuid4

from copenet.host.rpc_schema import ChatEventPayload, EventFrame, ResponseFrame, RpcError, make_chat_event, make_event_frame, make_response_frame
from copenet.core.orchestrator import ChatSendRequest, SessionInFlightError
from copenet.prompts import compose_prompt


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


def _optional_int(raw: dict[str, Any], key: str) -> int | None:
    value = raw.get(key)
    if value in (None, ""):
        return None
    return int(value)


@dataclass(frozen=True)
class ChatSendParams:
    session_key: str
    message: str
    run_id: str
    provider: str
    model: str | None
    system_prompt_id: str | None
    task_prompt_id: str | None
    persona_id: str | None
    persona_flavor_id: str | None
    persona_privacy_tier: str | None
    timeout_ms: int | None
    system_prompt: str | None
    workspace_root: str | None


def _normalize_chat_send_params(raw: dict[str, Any]) -> ChatSendParams:
    session_key = _required_text(raw, "sessionKey")
    message = _required_text(raw, "message")
    run_id = _optional_text(raw, "idempotencyKey") or str(uuid4())
    system_prompt_id = _optional_text(raw, "systemPromptId")
    task_prompt_id = _optional_text(raw, "taskPromptId")
    return ChatSendParams(
        session_key=session_key,
        message=message,
        run_id=run_id,
        provider=_optional_text(raw, "provider") or "codex-cli",
        model=_optional_text(raw, "model"),
        system_prompt_id=system_prompt_id,
        task_prompt_id=task_prompt_id,
        persona_id=_optional_text(raw, "personaId"),
        persona_flavor_id=_optional_text(raw, "personaFlavorId"),
        persona_privacy_tier=_optional_text(raw, "personaPrivacyTier"),
        timeout_ms=_optional_int(raw, "timeoutMs"),
        system_prompt=compose_prompt(system_prompt_id, task_prompt_id),
        workspace_root=_optional_text(raw, "workspaceRoot"),
    )


def _chat_event_payload(payload: dict[str, Any], default_run_id: str, default_session_key: str) -> ChatEventPayload:
    return ChatEventPayload(
        run_id=_optional_text(payload, "runId") or default_run_id,
        session_key=_optional_text(payload, "sessionKey") or default_session_key,
        seq=int(payload.get("seq") or 0),
        state=str(payload.get("state") or "error"),
        message=payload.get("message") if isinstance(payload.get("message"), dict) else None,
        error_message=_optional_text(payload, "errorMessage"),
        provider=_optional_text(payload, "provider"),
        model=_optional_text(payload, "model"),
        capabilities=payload.get("capabilities") if isinstance(payload.get("capabilities"), dict) else None,
        tool_execution=payload.get("toolExecution") if isinstance(payload.get("toolExecution"), dict) else None,
        tool_call=payload.get("toolCall") if isinstance(payload.get("toolCall"), dict) else None,
        turn_state=payload.get("turnState") if isinstance(payload.get("turnState"), dict) else None,
    )


async def handle_chat_send(
    request_id: str,
    params: dict[str, Any] | None,
    send_json: SendJson,
    tasks: set[asyncio.Task],
    orchestrator,
    broadcast: SendJson | None = None,
) -> None:
    # Stream chat + side events to EVERY connected client (the originating socket
    # is in that set too), so a reconnected socket or a second device keeps
    # receiving live frames. The direct request response stays point-to-point.
    emit_to = broadcast or send_json
    raw = params or {}
    request = _normalize_chat_send_params(raw)
    if not request.session_key or not request.message:
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

    await send_json(
        make_response_frame(
            ResponseFrame(id=request_id, ok=True, payload={"runId": request.run_id, "status": "started"})
        )
    )

    async def emit_chat(payload: dict[str, Any]) -> None:
        try:
            await emit_to(make_chat_event(_chat_event_payload(payload, request.run_id, request.session_key)))
        except Exception:
            # Live frames are best-effort after chat.send has been accepted.
            # The run should still complete and persist if the browser reconnects.
            return

    async def emit_side_event(event: str, payload: dict[str, Any]) -> None:
        try:
            await emit_to(make_event_frame(EventFrame(event=event, payload=payload)))
        except Exception:
            return

    async def run() -> None:
        try:
            await orchestrator.send_chat(
                ChatSendRequest(
                    session_key=request.session_key,
                    message=request.message,
                    idempotency_key=request.run_id,
                    provider=request.provider,
                    model=request.model,
                    system_prompt_id=request.system_prompt_id,
                    task_prompt_id=request.task_prompt_id,
                    persona_id=request.persona_id,
                    persona_flavor_id=request.persona_flavor_id,
                    persona_privacy_tier=request.persona_privacy_tier,  # type: ignore[arg-type]
                    timeout_ms=request.timeout_ms,
                    system_prompt=request.system_prompt,
                    workspace_root=request.workspace_root,
                ),
                emit=emit_chat,
                emit_event=emit_side_event,
            )
        except SessionInFlightError as exc:
            try:
                await send_json(
                    make_response_frame(
                        ResponseFrame(
                            id=request_id,
                            ok=True,
                            payload={"runId": exc.run_id, "status": "in_flight"},
                        )
                    )
                )
            except Exception:
                return
        except Exception as exc:
            await emit_chat(
                {
                    "runId": request.run_id,
                    "sessionKey": request.session_key,
                    "seq": 1,
                    "state": "error",
                    "errorMessage": str(exc),
                }
            )

    task = asyncio.create_task(run())
    tasks.add(task)

    def finalize_task(done: asyncio.Task) -> None:
        tasks.discard(done)
        if done.cancelled():
            return
        try:
            done.exception()
        except Exception:
            return

    task.add_done_callback(finalize_task)


async def handle_chat_abort(request_id: str, params: dict[str, Any] | None, send_json: SendJson, orchestrator) -> None:
    raw = params or {}
    session_key = _required_text(raw, "sessionKey")
    run_id = _optional_text(raw, "runId")
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
    session_key = _required_text(raw, "sessionKey")
    limit = _optional_int(raw, "limit") or 200
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
