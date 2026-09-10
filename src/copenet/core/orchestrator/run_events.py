"""Accumulate provider events and publish ordered chat activity."""

from __future__ import annotations


from copenet.providers import RESOLVED_MODEL_META_KEY

from .run_types import RunAdmission, RunInput, RunEvents
from .run_message_parts import _append_text_part, _append_thinking_part, _replay_output_from_runtime_input
from copenet.core.tools.receipts import normalize_tool_step


async def consume_reasoning(
    orchestrator, admission: RunAdmission, prepared: RunInput, events: RunEvents, event, emit
):
    reasoning_source = str((event.metadata or {}).get("reasoningSource") or "summary")
    provider_event_type = str((event.metadata or {}).get("providerEventType") or "") or None
    _append_thinking_part(events.assistant_message_parts, event.text, source=reasoning_source)
    admission.trace.record(
        "reasoning_delta",
        {"chars": len(event.text), "source": reasoning_source, "providerEventType": provider_event_type},
    )
    admission.trace.record_debug(
        "reasoning_content",
        {"text": event.text, "source": reasoning_source, "providerEventType": provider_event_type},
    )
    events.seq += 1
    await emit(
        {
            "runId": admission.run_id,
            "sessionKey": admission.session_key,
            "seq": events.seq,
            "state": "reasoning_delta",
            "provider": admission.provider_name,
            "model": admission.request.model,
            "text": event.text,
            "reasoningSource": reasoning_source,
        }
    )


async def consume_metadata(
    orchestrator, admission: RunAdmission, prepared: RunInput, events: RunEvents, event, emit
):
    announced = event.metadata.get(RESOLVED_MODEL_META_KEY)
    if isinstance(announced, str) and announced.strip() and (announced.strip() != events.resolved_model):
        events.resolved_model = announced.strip()
        admission.trace.model = events.resolved_model
        admission.trace.record(
            "model_resolved",
            {"requestedModel": admission.request.model, "resolvedModel": events.resolved_model},
        )
    tool_call_payload = event.metadata.get("toolCall")
    if isinstance(tool_call_payload, dict):
        events.assistant_message_parts.append({"kind": "tool_call", "toolCall": dict(tool_call_payload)})
        events.seq += 1
        await emit(
            {
                "runId": admission.run_id,
                "sessionKey": admission.session_key,
                "seq": events.seq,
                "state": "tool_called",
                "provider": admission.provider_name,
                "model": admission.request.model,
                "toolCall": dict(tool_call_payload),
                "turnState": event.metadata.get("turnState")
                if isinstance(event.metadata.get("turnState"), dict)
                else None,
            }
        )
    tool_payload = event.metadata.get("toolExecution")
    if isinstance(tool_payload, dict):
        events.tool_execution_payload = tool_payload
        stored_execution = dict(tool_payload)
        replay_output = _replay_output_from_runtime_input(event.metadata.get("toolResult"))
        if replay_output:
            stored_execution["replayOutput"] = replay_output
        events.assistant_message_parts.append({"kind": "tool_result", "toolExecution": stored_execution})
        events.tool_steps.append(normalize_tool_step(tool_payload))
        artifact_id = str(tool_payload.get("artifactId") or "").strip()
        if artifact_id and artifact_id not in events.persisted_tool_artifact_ids:
            events.persisted_tool_artifact_ids.append(artifact_id)
        events.seq += 1
        await emit(
            {
                "runId": admission.run_id,
                "sessionKey": admission.session_key,
                "seq": events.seq,
                "state": "tool_result",
                "provider": admission.provider_name,
                "model": admission.request.model,
                "toolExecution": dict(tool_payload),
                "turnState": event.metadata.get("turnState")
                if isinstance(event.metadata.get("turnState"), dict)
                else None,
            }
        )
    tool_result_payload = event.metadata.get("toolResult")
    if isinstance(tool_result_payload, dict):
        events.normalized_tool_results.append(dict(tool_result_payload))
        admission.trace.record_debug("tool_result_body", dict(tool_result_payload))
    turn_state_payload = event.metadata.get("turnState")
    if isinstance(turn_state_payload, dict):
        events.latest_turn_state = dict(turn_state_payload)
    artifact_draft = event.metadata.get("artifactDraft")
    if isinstance(artifact_draft, dict):
        events.artifact_drafts.append(artifact_draft)


async def consume_text(
    orchestrator, admission: RunAdmission, prepared: RunInput, events: RunEvents, event, emit
):
    events.assistant_parts.append(event.text)
    _append_text_part(events.assistant_message_parts, event.text)
    events.seq += 1
    await emit(
        {
            "runId": admission.run_id,
            "sessionKey": admission.session_key,
            "seq": events.seq,
            "state": "delta",
            "message": {
                "role": "assistant",
                "content": event.text,
                "parts": [dict(part) for part in events.assistant_message_parts],
                "provider": admission.provider_name,
                "model": admission.request.model,
            },
            "provider": admission.provider_name,
            "model": admission.request.model,
            "capabilities": {
                "toolCalls": events.plan.capability_profile.tool_calls,
                "promptedToolUse": events.plan.capability_profile.prompted_tool_use,
            },
            "toolExecution": events.tool_execution_payload,
        }
    )


async def consume_event(
    orchestrator, admission: RunAdmission, prepared: RunInput, events: RunEvents, event, emit
):
    if event.provider_session_id and event.provider_session_id != admission.entry.provider_session_id:
        admission.entry = orchestrator._session_store.update_provider_session_id(
            session_key=admission.session_key, provider_session_id=event.provider_session_id
        )
        admission.trace.record("provider_session_updated", {"providerSessionId": event.provider_session_id})
    if event.kind == "reasoning_delta" and event.text:
        await consume_reasoning(orchestrator, admission, prepared, events, event, emit)
    elif event.kind == "meta" and isinstance(event.metadata, dict):
        await consume_metadata(orchestrator, admission, prepared, events, event, emit)
    elif event.kind == "delta" and event.text:
        await consume_text(orchestrator, admission, prepared, events, event, emit)
