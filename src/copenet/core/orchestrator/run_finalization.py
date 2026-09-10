"""Persist terminal execution outcomes independently of event delivery."""

from __future__ import annotations
from copenet.core.runtime import RunRecord
from copenet.core.sessions import TranscriptMessage
from copenet.core.sessions.transcript_store import utc_now_iso as transcript_now
from copenet.core.tools import describe_available_tools
from .run_types import RunAdmission, RunInput, RunEvents
from .run_message_parts import _normalize_final_message_parts
from .run_state import _evolve_session_state, _build_tool_visibility_summary
from .market_context import update_chart_admission


def persist_artifacts(orchestrator, admission: RunAdmission, events: RunEvents, assistant_text: str):
    events.created_artifact_ids = list(events.persisted_tool_artifact_ids)
    if events.chart_manifest_id:
        events.created_artifact_ids.append(events.chart_manifest_id)
    for draft in events.artifact_drafts:
        created = orchestrator._artifact_store.create(
            session_key=admission.session_key,
            run_id=admission.run_id,
            artifact_type=str(draft.get("type") or "tool_bundle"),
            title=str(draft.get("title") or "Runtime artifact"),
            body=str(draft.get("body") or ""),
            source_asset_ids=list(draft.get("source_asset_ids") or []),
            source_artifact_ids=list(draft.get("source_artifact_ids") or []),
            metadata=dict(draft.get("metadata") or {}),
        )
        events.created_artifact_ids.append(created.artifact_id)
        admission.trace.record(
            "artifact_created",
            {"artifactId": created.artifact_id, "type": created.type, "title": created.title},
        )
    if assistant_text:
        answer_artifact = orchestrator._artifact_store.create(
            session_key=admission.session_key,
            run_id=admission.run_id,
            artifact_type="answer",
            title=f"Answer for {admission.session_key}",
            body=assistant_text,
            source_artifact_ids=events.created_artifact_ids,
            metadata={
                "provider": admission.provider_name,
                "model": events.resolved_model or admission.request.model,
            },
        )
        events.created_artifact_ids.append(answer_artifact.artifact_id)
        admission.trace.record(
            "artifact_created",
            {
                "artifactId": answer_artifact.artifact_id,
                "type": answer_artifact.type,
                "title": answer_artifact.title,
            },
        )


def persist_assistant(
    orchestrator, admission: RunAdmission, events: RunEvents, assistant_text: str, state: str
):
    if not events.transcript_persisted and (assistant_text or events.assistant_message_parts):
        orchestrator._transcript_store.append_message(
            admission.entry.session_id,
            TranscriptMessage(
                run_id=admission.run_id,
                role="assistant",
                content=assistant_text,
                provider=admission.provider_name,
                model=events.resolved_model or admission.request.model,
                provider_session_id=admission.entry.provider_session_id,
                timestamp=transcript_now(),
                state=state,
                market_context=admission.market_reference,
                tool_execution=events.tool_execution_payload,
                parts=[dict(part) for part in events.assistant_message_parts]
                if events.assistant_message_parts
                else None,
            ),
        )
        events.transcript_persisted = True
        admission.trace.record(
            "assistant_finalized",
            {
                "responseLength": len(assistant_text),
                "toolExecutionAttached": bool(events.tool_execution_payload),
                "partsCount": len(events.assistant_message_parts) if events.assistant_message_parts else 0,
                "toolOnly": bool(not assistant_text and events.assistant_message_parts),
            },
        )


def successful_record(
    orchestrator, admission: RunAdmission, prepared: RunInput, events: RunEvents, assistant_text: str
):
    updated_state = _evolve_session_state(
        session_state=prepared.session_state,
        run_id=admission.run_id,
        plan=events.plan,
        task_prompt_id=admission.entry.task_prompt_id or admission.request.task_prompt_id,
        created_artifact_ids=events.created_artifact_ids,
    )
    orchestrator._session_state_store.save(updated_state)
    admission.trace.record(
        "state_updated",
        {
            "sessionKey": admission.session_key,
            "relevantArtifactCount": len(updated_state.relevant_artifact_ids),
        },
    )
    run_record = RunRecord(
        run_id=admission.run_id,
        session_key=admission.session_key,
        provider=admission.provider_name,
        model=events.resolved_model or admission.request.model,
        status="ok",
        user_message=admission.message,
        tool_execution_mode=events.plan.tool_execution_mode,
        will_attempt_tool_loop=events.plan.will_attempt_tool_loop,
        started_at=admission.run_started_at,
        completed_at=transcript_now(),
        working_set={},
        message_count=prepared.message_count,
        input_token_estimate=prepared.input_token_estimate,
        tool_steps=events.tool_steps,
        artifact_ids=events.created_artifact_ids,
        output_summary=assistant_text.strip()[:240],
        transition_reason=str(events.latest_turn_state.get("transitionReason") or "completed"),
        terminal_reason=str(events.latest_turn_state.get("terminalReason") or "completed"),
        tool_results=events.normalized_tool_results,
        pending_input_count=int(events.latest_turn_state.get("pendingInputCount") or 0),
        oversized_tool_artifact_ids=list(events.persisted_tool_artifact_ids),
        metadata={
            **admission.market_metadata,
            "capabilityProfile": {
                "toolCalls": events.plan.capability_profile.tool_calls,
                "promptedToolUse": events.plan.capability_profile.prompted_tool_use,
            },
            **prepared.agent_runtime_payload,
            "delegatedTasks": list(prepared.agent_runtime_payload.get("delegatedTasks") or []),
            "toolManifest": describe_available_tools(events.plan.tools),
            "toolVisibility": _build_tool_visibility_summary(events.plan.tools),
            "harnessDecision": dict(events.plan.harness_decision),
            "policySummary": {
                "allowedCategories": sorted(prepared.tools.effective_tool_policy.allowed_categories),
                "shellAllowlist": list(prepared.tools.effective_tool_policy.shell_allowlist),
            },
            "workspaceRoot": str(admission.session_workspace_root),
            "requestedToolIds": list(prepared.tools.requested_tool_ids),
            "activeRequestedToolIds": list(prepared.tools.active_requested_tool_ids),
            "rejectedRequestedToolIds": list(prepared.tools.rejected_requested_tool_ids),
            "turnState": dict(events.latest_turn_state),
            "identityContext": dict(prepared.identity_context_payload),
        },
    )
    return run_record


def final_frame(admission: RunAdmission, prepared: RunInput, events: RunEvents, assistant_text: str):
    events.seq += 1
    final_payload = {
        "runId": admission.run_id,
        "sessionKey": admission.session_key,
        "seq": events.seq,
        "state": "final",
        "message": {
            "role": "assistant",
            "content": assistant_text,
            "parts": [dict(part) for part in events.assistant_message_parts],
            "provider": admission.provider_name,
            "model": events.resolved_model or admission.request.model,
        }
        if assistant_text
        else None,
        "provider": admission.provider_name,
        "model": events.resolved_model or admission.request.model,
        "capabilities": {
            "toolCalls": events.plan.capability_profile.tool_calls,
            "promptedToolUse": events.plan.capability_profile.prompted_tool_use,
        },
        "toolExecution": events.tool_execution_payload,
        "turnState": events.latest_turn_state or None,
        "harnessDecision": dict(events.plan.harness_decision),
        "identityContext": prepared.identity_context_payload,
        "agentContext": prepared.agent_runtime_payload,
    }
    return final_payload


def persist_terminal(
    orchestrator, admission: RunAdmission, events: RunEvents, record: RunRecord, payload: dict
) -> None:
    """There is one terminal write; notification cannot replace its outcome."""
    orchestrator._run_store.create(record)
    events.terminal_persisted = True
    if admission.dedupe_key is not None:
        orchestrator._idempotency_cache[admission.dedupe_key] = payload
    # No await between the terminal append, cache update and admission update.
    state = {"ok": "completed", "error": "failed", "interrupted": "interrupted"}[record.status]
    update_chart_admission(orchestrator, admission.request, state)
    admission.trace.record(
        "run_record_created",
        {
            "runId": record.run_id,
            "status": record.status,
            "toolStepCount": len(record.tool_steps),
            "artifactCount": len(record.artifact_ids),
        },
    )


def finish_success(orchestrator, admission: RunAdmission, prepared: RunInput, events: RunEvents):
    assistant_text = "".join(events.assistant_parts).strip()
    events.assistant_message_parts = _normalize_final_message_parts(
        events.assistant_message_parts, assistant_text=assistant_text
    )
    persist_artifacts(orchestrator, admission, events, assistant_text)
    persist_assistant(
        orchestrator, admission, events, assistant_text, "final" if assistant_text else "tool_only"
    )
    record = successful_record(orchestrator, admission, prepared, events, assistant_text)
    payload = final_frame(admission, prepared, events, assistant_text)
    persist_terminal(orchestrator, admission, events, record, payload)
    admission.trace.record(
        "run_completed", {"status": "ok", "toolExecutionAttached": bool(events.tool_execution_payload)}
    )
    return record, payload


def finish_failure(
    orchestrator,
    admission: RunAdmission,
    prepared: RunInput | None,
    events: RunEvents,
    exc: BaseException,
    *,
    interrupted: bool = False,
) -> dict:
    status = "interrupted" if interrupted else "error"
    reason = "aborted" if interrupted else "model_error"
    assistant_text = "".join(events.assistant_parts).strip()
    # Preserve the activity as observed, including unpaired calls. Replay already
    # drops calls with no result; the inspector still needs the attempted action.
    persist_assistant(orchestrator, admission, events, assistant_text, status)
    artifact_ids = list(dict.fromkeys([*events.created_artifact_ids, *events.persisted_tool_artifact_ids]))
    if events.chart_manifest_id and events.chart_manifest_id not in artifact_ids:
        artifact_ids.append(events.chart_manifest_id)
    metadata = {**admission.market_metadata, "workspaceRoot": str(admission.session_workspace_root)}
    if prepared is not None:
        metadata.update(
            {
                "requestedToolIds": list(prepared.tools.requested_tool_ids),
                "activeRequestedToolIds": list(prepared.tools.active_requested_tool_ids),
                "rejectedRequestedToolIds": list(prepared.tools.rejected_requested_tool_ids),
                **prepared.agent_runtime_payload,
            }
        )
    if events.plan is not None:
        metadata["harnessDecision"] = dict(events.plan.harness_decision)
    record = RunRecord(
        run_id=admission.run_id,
        session_key=admission.session_key,
        provider=admission.provider_name,
        model=events.resolved_model or admission.request.model,
        status=status,
        user_message=admission.message,
        tool_execution_mode=events.plan.tool_execution_mode if events.plan else "none",
        will_attempt_tool_loop=events.plan.will_attempt_tool_loop if events.plan else False,
        started_at=admission.run_started_at,
        completed_at=transcript_now(),
        message_count=prepared.message_count if prepared else 0,
        input_token_estimate=prepared.input_token_estimate if prepared else 0,
        tool_steps=events.tool_steps,
        artifact_ids=artifact_ids,
        output_summary=assistant_text[:240],
        error=str(exc) or reason,
        transition_reason=events.latest_turn_state.get("transitionReason") or reason,
        terminal_reason=reason,
        tool_results=events.normalized_tool_results,
        pending_input_count=events.latest_turn_state.get("pendingInputCount", 0),
        oversized_tool_artifact_ids=list(events.persisted_tool_artifact_ids),
        metadata=metadata,
    )
    events.seq += 1
    payload = {
        "runId": admission.run_id,
        "sessionKey": admission.session_key,
        "seq": events.seq,
        "state": "error",
        "errorMessage": str(exc) or "Run interrupted",
        "provider": admission.provider_name,
        "model": events.resolved_model or admission.request.model,
    }
    persist_terminal(orchestrator, admission, events, record, payload)
    admission.trace.record(
        "run_failed",
        {"phase": "send_chat", "error": str(exc), "errorType": type(exc).__name__, "status": status},
    )
    return payload
