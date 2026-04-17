"""Run lifecycle helpers for the orchestrator."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING
from uuid import uuid4

from copenet.core.orchestrator.working_set import assemble_working_set
from copenet.core.runtime import RunRecord
from copenet.core.sessions import SessionStateRecord
from copenet.core.sessions import TranscriptMessage
from copenet.core.sessions.transcript_store import utc_now_iso as transcript_now
from copenet.core.tools import ToolExecutionContext
from copenet.core.tracing import RunTraceWriter

if TYPE_CHECKING:
    from . import ChatSendRequest, Orchestrator


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
    working_history = orchestrator.history(session_key=session_key, limit=12)
    is_first_turn = len(prior_history) == 0
    run_started_at = transcript_now()
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
            from . import SessionInFlightError

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
    session_state = orchestrator._session_state_store.get_or_create(session_key)
    trace.record(
        "state_loaded",
        {
            "sessionKey": session_key,
            "relevantArtifactCount": len(session_state.relevant_artifact_ids),
            "relevantAssetCount": len(session_state.relevant_asset_ids),
            "workingSetRefCount": len(session_state.working_set_refs),
        },
    )
    working_set = assemble_working_set(
        user_message=message,
        session_state=session_state,
        transcript_window=working_history,
        artifact_store=orchestrator._artifact_store,
        system_prompt=request.system_prompt,
        session_key=session_key,
    )
    trace.record("working_set_assembled", working_set.metadata)

    provider = orchestrator._providers[provider_name]
    seq = 0
    assistant_parts: list[str] = []
    tool_execution_payload: dict | None = None
    latest_turn_state: dict = {}
    normalized_tool_results: list[dict] = []
    artifact_drafts: list[dict] = []
    tool_steps: list[dict] = []
    persisted_tool_artifact_ids: list[str] = []
    try:
        plan, event_stream = await orchestrator._harness.run_turn(
            provider=provider,
            prompt=working_set.prompt,
            provider_session_id=entry.provider_session_id,
            abort_event=abort_event,
            model=request.model,
            system_prompt=request.system_prompt,
            available_tools=orchestrator._tool_registry.list_tools() if request.allow_tools else [],
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
                artifact_store=orchestrator._artifact_store,
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
                    tool_steps.append(_normalize_tool_step(tool_payload))
                    artifact_id = str(tool_payload.get("artifactId") or "").strip()
                    if artifact_id and artifact_id not in persisted_tool_artifact_ids:
                        persisted_tool_artifact_ids.append(artifact_id)
                tool_result_payload = event.metadata.get("toolResult")
                if isinstance(tool_result_payload, dict):
                    normalized_tool_results.append(dict(tool_result_payload))
                    trace.record("tool_result_normalized", dict(tool_result_payload))
                turn_state_payload = event.metadata.get("turnState")
                if isinstance(turn_state_payload, dict):
                    latest_turn_state = dict(turn_state_payload)
                artifact_draft = event.metadata.get("artifactDraft")
                if isinstance(artifact_draft, dict):
                    artifact_drafts.append(artifact_draft)

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
                            "promptedToolUse": plan.capability_profile.prompted_tool_use,
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
        created_artifact_ids: list[str] = list(persisted_tool_artifact_ids)
        for draft in artifact_drafts:
            created = orchestrator._artifact_store.create(
                session_key=session_key,
                run_id=run_id,
                artifact_type=str(draft.get("type") or "tool_bundle"),
                title=str(draft.get("title") or "Runtime artifact"),
                body=str(draft.get("body") or ""),
                source_asset_ids=list(draft.get("source_asset_ids") or []),
                source_artifact_ids=list(draft.get("source_artifact_ids") or []),
                metadata=dict(draft.get("metadata") or {}),
            )
            created_artifact_ids.append(created.artifact_id)
            trace.record(
                "artifact_created",
                {
                    "artifactId": created.artifact_id,
                    "type": created.type,
                    "title": created.title,
                },
            )
        if assistant_text:
            answer_artifact = orchestrator._artifact_store.create(
                session_key=session_key,
                run_id=run_id,
                artifact_type="answer",
                title=f"Answer for {session_key}",
                body=assistant_text,
                source_artifact_ids=created_artifact_ids,
                metadata={"provider": provider_name, "model": request.model},
            )
            created_artifact_ids.append(answer_artifact.artifact_id)
            trace.record(
                "artifact_created",
                {
                    "artifactId": answer_artifact.artifact_id,
                    "type": answer_artifact.type,
                    "title": answer_artifact.title,
                },
            )
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

        updated_state = _evolve_session_state(
            session_state=session_state,
            message=message,
            run_id=run_id,
            plan=plan,
            working_set=working_set.metadata,
            tool_execution_payload=tool_execution_payload,
            created_artifact_ids=created_artifact_ids,
        )
        orchestrator._session_state_store.save(updated_state)
        trace.record(
            "state_updated",
            {
                "sessionKey": session_key,
                "relevantArtifactCount": len(updated_state.relevant_artifact_ids),
                "activeEntityCount": len(updated_state.active_entities),
            },
        )
        run_record = RunRecord(
            run_id=run_id,
            session_key=session_key,
            provider=provider_name,
            model=request.model,
            status="ok",
            user_message=message,
            tool_execution_mode=plan.tool_execution_mode,
            will_attempt_tool_loop=plan.will_attempt_tool_loop,
            started_at=run_started_at,
            completed_at=transcript_now(),
            working_set=dict(working_set.metadata),
            tool_steps=tool_steps,
            artifact_ids=created_artifact_ids,
            output_summary=_summarize_output(assistant_text),
            transition_reason=str(latest_turn_state.get("transitionReason") or "completed"),
            terminal_reason=str(latest_turn_state.get("terminalReason") or "completed"),
            tool_results=normalized_tool_results,
            pending_input_count=int(latest_turn_state.get("pendingInputCount") or 0),
            oversized_tool_artifact_ids=list(persisted_tool_artifact_ids),
            metadata={
                "capabilityProfile": {
                    "toolCalls": plan.capability_profile.tool_calls,
                    "promptedToolUse": plan.capability_profile.prompted_tool_use,
                },
                "turnState": dict(latest_turn_state),
            },
        )
        orchestrator._run_store.create(run_record)
        trace.record(
            "run_record_created",
            {
                "runId": run_record.run_id,
                "status": run_record.status,
                "toolStepCount": len(run_record.tool_steps),
                "artifactCount": len(run_record.artifact_ids),
            },
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
                "promptedToolUse": plan.capability_profile.prompted_tool_use,
            },
            "toolExecution": tool_execution_payload,
            "turnState": latest_turn_state or None,
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
        failed_run = RunRecord(
            run_id=run_id,
            session_key=session_key,
            provider=provider_name,
            model=request.model,
            status="error",
            user_message=message,
            tool_execution_mode=plan.tool_execution_mode if "plan" in locals() else "none",
            will_attempt_tool_loop=plan.will_attempt_tool_loop if "plan" in locals() else False,
            started_at=run_started_at,
            completed_at=transcript_now(),
            working_set=dict(working_set.metadata) if "working_set" in locals() else {},
            tool_steps=tool_steps,
            artifact_ids=list(persisted_tool_artifact_ids),
            output_summary="",
            error=str(exc),
            transition_reason=str(latest_turn_state.get("transitionReason") or "model_error"),
            terminal_reason="model_error",
            tool_results=normalized_tool_results,
            pending_input_count=int(latest_turn_state.get("pendingInputCount") or 0),
            oversized_tool_artifact_ids=list(persisted_tool_artifact_ids),
        )
        orchestrator._run_store.create(failed_run)
        trace.record(
            "run_record_created",
            {
                "runId": failed_run.run_id,
                "status": failed_run.status,
                "toolStepCount": len(failed_run.tool_steps),
                "artifactCount": 0,
            },
        )
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


def _evolve_session_state(
    *,
    session_state: SessionStateRecord,
    message: str,
    run_id: str,
    plan,
    working_set: dict,
    tool_execution_payload: dict | None,
    created_artifact_ids: list[str],
) -> SessionStateRecord:
    relevant_artifact_ids = _append_unique(
        session_state.relevant_artifact_ids,
        created_artifact_ids,
    )[-10:]
    active_entities = list(session_state.active_entities)
    tool_id = str((tool_execution_payload or {}).get("toolId") or "").strip()
    if tool_id:
        active_entities = _append_unique(active_entities, [tool_id])[-10:]
    return SessionStateRecord(
        session_key=session_state.session_key,
        task_summary=message.strip(),
        goals=list(session_state.goals),
        active_entities=active_entities,
        working_set_refs=_append_unique(
            list(session_state.working_set_refs),
            [
                *list(working_set.get("artifactIds") or []),
                *list(working_set.get("assetIds") or []),
            ],
        )[-10:],
        constraints=list(session_state.constraints),
        unresolved_questions=list(session_state.unresolved_questions),
        prior_decisions=_append_unique(
            list(session_state.prior_decisions),
            [f"Run {run_id} completed with tool mode {plan.tool_execution_mode}"],
        )[-10:],
        plan_snapshot={
            "runId": run_id,
            "toolExecutionMode": plan.tool_execution_mode,
            "willAttemptToolLoop": plan.will_attempt_tool_loop,
        },
        relevant_asset_ids=list(session_state.relevant_asset_ids),
        relevant_artifact_ids=relevant_artifact_ids,
        created_at=session_state.created_at,
        updated_at=transcript_now(),
    )


def _append_unique(existing: list[str], incoming: list[str]) -> list[str]:
    rows = list(existing)
    for item in incoming:
        text = str(item).strip()
        if text and text not in rows:
            rows.append(text)
    return rows


def _normalize_tool_step(tool_payload: dict) -> dict:
    return {
        "callId": str(tool_payload.get("callId") or "").strip() or None,
        "toolId": str(tool_payload.get("toolId") or "").strip(),
        "channel": str(tool_payload.get("channel") or "tool").strip(),
        "ok": bool(tool_payload.get("ok")),
        "summary": str(tool_payload.get("summary") or ""),
        "error": str(tool_payload.get("error")).strip() if tool_payload.get("error") is not None else None,
        "artifactId": str(tool_payload.get("artifactId") or "").strip() or None,
        "status": "blocked" if tool_payload.get("ok") is False else "ok",
        "batched": str(tool_payload.get("channel") or "") == "batch" or str(tool_payload.get("toolId") or "") == "tool.batch",
    }


def _summarize_output(text: str) -> str:
    return " ".join(text.split())[:240]
