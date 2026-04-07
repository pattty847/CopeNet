"""Run lifecycle helpers for the orchestrator facade."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING
from uuid import uuid4

from copenet.sessions import TranscriptMessage
from copenet.sessions.transcript_store import utc_now_iso as transcript_now
from copenet.tools import ToolExecutionContext
from copenet.tracing import RunTraceWriter

if TYPE_CHECKING:
    from copenet.orchestrator import ChatSendRequest, Orchestrator


async def send_chat(orchestrator: "Orchestrator", request: "ChatSendRequest", emit) -> dict:
    """Start one chat run and stream events through `emit` callback."""
    session_key = request.session_key.strip()
    message = request.message.strip()
    if not session_key:
        raise ValueError("session_key is required")
    if not message:
        raise ValueError("message is required")

    run_id = request.idempotency_key.strip() if request.idempotency_key else str(uuid4())
    provider_name = request.provider.strip() or "codex-cli"
    if provider_name not in orchestrator._providers:
        init_error = orchestrator._provider_init_errors.get(provider_name)
        if init_error:
            raise RuntimeError(f"provider unavailable: {provider_name} ({init_error})")
        raise ValueError(f"unsupported provider: {provider_name}")

    dedupe_key = f"chat:{run_id}"
    prior_history = orchestrator.history(session_key=session_key, limit=2)
    is_first_turn = len(prior_history) == 0
    trace = RunTraceWriter(
        run_id=run_id,
        session_key=session_key,
        provider=provider_name,
        model=request.model,
        enabled=orchestrator._trace_enabled,
    )
    async with orchestrator._lock:
        cached = orchestrator._idempotency_cache.get(dedupe_key)
        if cached is not None:
            return {"runId": run_id, "status": "cached", "cached": True, "result": cached}

        active_run = orchestrator._active_run_by_session.get(session_key)
        if active_run and active_run != run_id:
            from copenet.orchestrator import SessionInFlightError

            raise SessionInFlightError(active_run)

        entry = orchestrator._session_store.resolve_or_create(
            session_key=session_key,
            provider=provider_name,
            model=request.model,
            system_prompt_id=request.system_prompt_id,
            task_prompt_id=request.task_prompt_id,
        )
        entry = orchestrator._session_store.assert_session_binding(
            session_key=session_key,
            provider=provider_name,
            model=request.model,
            system_prompt_id=request.system_prompt_id,
            task_prompt_id=request.task_prompt_id,
        )
        orchestrator._session_store.mark_run_started(session_key=session_key, run_id=run_id)
        abort_event = asyncio.Event()
        orchestrator._active_abort_by_run[run_id] = abort_event
        orchestrator._active_run_by_session[session_key] = run_id

    trace.record(
        "run_started",
        {
            "messagePreview": message[:200],
            "profile": request.system_prompt_id,
            "taskMode": request.task_prompt_id,
            "workdir": str(orchestrator._workdir),
        },
    )
    trace.record(
        "session_resolved",
        {
            "providerSessionId": entry.provider_session_id,
            "sessionId": entry.session_id,
        },
    )

    orchestrator._transcript_store.append_message(
        entry.session_id,
        TranscriptMessage(
            run_id=run_id,
            role="user",
            content=message,
            provider=provider_name,
            model=request.model,
            provider_session_id=entry.provider_session_id,
            timestamp=transcript_now(),
        ),
    )

    provider = orchestrator._providers[provider_name]
    seq = 0
    assistant_parts: list[str] = []
    tool_execution_payload: dict | None = None
    try:
        plan, event_stream = await orchestrator._harness.run_turn(
            provider=provider,
            prompt=message,
            provider_session_id=entry.provider_session_id,
            abort_event=abort_event,
            model=request.model,
            system_prompt=request.system_prompt,
            available_tools=orchestrator._tool_registry.list_tools(),
            tool_executor=orchestrator._tool_registry.execute,
            tool_context=ToolExecutionContext(
                workdir=orchestrator._workdir,
                session_key=session_key,
                provider_name=provider_name,
                model=request.model,
                session_store=orchestrator._session_store,
                transcript_store=orchestrator._transcript_store,
                providers=orchestrator._providers,
                policy=orchestrator._tool_policy,
                trace=trace.record,
            ),
            trace=trace.record,
        )
        if not plan.will_attempt_tool_loop:
            trace.record(
                "provider_turn_started",
                {
                    "phase": "provider",
                    "providerSessionId": entry.provider_session_id,
                },
            )
        async for event in event_stream:
            if event.provider_session_id and event.provider_session_id != entry.provider_session_id:
                entry = orchestrator._session_store.update_provider_session_id(
                    session_key=session_key,
                    provider_session_id=event.provider_session_id,
                )
                trace.record(
                    "provider_session_updated",
                    {
                        "providerSessionId": event.provider_session_id,
                    },
                )

            if event.kind == "meta" and isinstance(event.metadata, dict):
                tool_payload = event.metadata.get("toolExecution")
                if isinstance(tool_payload, dict):
                    tool_execution_payload = tool_payload

            if event.kind == "delta" and event.text:
                assistant_parts.append(event.text)
                seq += 1
                await emit(
                    {
                        "runId": run_id,
                        "sessionKey": session_key,
                        "seq": seq,
                        "state": "delta",
                        "message": {
                            "role": "assistant",
                            "content": event.text,
                            "provider": provider_name,
                            "model": request.model,
                        },
                        "provider": provider_name,
                        "model": request.model,
                        "capabilities": {
                            "toolCalls": plan.capability_profile.tool_calls,
                        },
                        "toolExecution": tool_execution_payload,
                    }
                )
            elif event.kind == "final":
                break

        if not plan.will_attempt_tool_loop:
            trace.record(
                "provider_turn_completed",
                {
                    "phase": "provider",
                    "providerSessionId": entry.provider_session_id,
                    "deltaCount": len(assistant_parts),
                },
            )

        assistant_text = "".join(part for part in assistant_parts if part).strip()
        if assistant_text:
            orchestrator._transcript_store.append_message(
                entry.session_id,
                TranscriptMessage(
                    run_id=run_id,
                    role="assistant",
                    content=assistant_text,
                    provider=provider_name,
                    model=request.model,
                    provider_session_id=entry.provider_session_id,
                    timestamp=transcript_now(),
                    state="final",
                    tool_execution=tool_execution_payload,
                ),
            )
            trace.record(
                "assistant_finalized",
                {
                    "responseLength": len(assistant_text),
                    "toolExecutionAttached": bool(tool_execution_payload),
                },
            )
            if is_first_turn and not (entry.title or "").strip():
                orchestrator._schedule_title_generation(
                    session_key=session_key,
                    provider_name=provider_name,
                    model=request.model,
                    first_user_message=message,
                    first_assistant_message=assistant_text,
                )

        seq += 1
        final_payload = {
            "runId": run_id,
            "sessionKey": session_key,
            "seq": seq,
            "state": "final",
            "message": {
                "role": "assistant",
                "content": assistant_text,
                "provider": provider_name,
                "model": request.model,
            }
            if assistant_text
            else None,
            "provider": provider_name,
            "model": request.model,
            "capabilities": {
                "toolCalls": plan.capability_profile.tool_calls,
            },
            "toolExecution": tool_execution_payload,
        }
        await emit(final_payload)
        trace.record(
            "run_completed",
            {
                "status": "ok",
                "toolExecutionAttached": bool(tool_execution_payload),
            },
        )
        async with orchestrator._lock:
            orchestrator._idempotency_cache[dedupe_key] = final_payload
        return {"runId": run_id, "status": "ok"}
    except Exception as exc:
        seq += 1
        error_payload = {
            "runId": run_id,
            "sessionKey": session_key,
            "seq": seq,
            "state": "error",
            "errorMessage": str(exc),
            "provider": provider_name,
            "model": request.model,
        }
        await emit(error_payload)
        trace.record(
            "run_failed",
            {
                "phase": "send_chat",
                "error": str(exc),
            },
        )
        async with orchestrator._lock:
            orchestrator._idempotency_cache[dedupe_key] = error_payload
        return {"runId": run_id, "status": "error", "summary": str(exc)}
    finally:
        async with orchestrator._lock:
            orchestrator._active_abort_by_run.pop(run_id, None)
            if orchestrator._active_run_by_session.get(session_key) == run_id:
                orchestrator._active_run_by_session.pop(session_key, None)
        orchestrator._session_store.mark_run_finished(session_key=session_key, run_id=run_id)
