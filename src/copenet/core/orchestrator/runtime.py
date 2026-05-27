"""Run lifecycle helpers for the orchestrator."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from copenet.core._config import (
    auto_memory_extraction_enabled,
    auto_profile_extraction_enabled,
)
from copenet.core.orchestrator.messages import (
    build_chat_messages,
    estimate_input_tokens,
    flatten_messages_to_prompt,
)
from copenet.core.runtime import RunRecord
from copenet.core.sessions import SessionStateRecord
from copenet.core.sessions import TranscriptMessage
from copenet.core.sessions.transcript_store import utc_now_iso as transcript_now
from copenet.core.tools import (
    ToolExecutionContext,
    describe_available_tools,
    policy_for_task_mode,
)
from copenet.core.tracing import RunTraceWriter

# Providers that maintain their own conversation thread and resume it via
# provider_session_id — they must NOT be re-fed the flattened transcript.
_RESUME_CLI_PROVIDERS = {"claude-cli", "codex-cli"}

if TYPE_CHECKING:
    from . import ChatSendRequest, Orchestrator


async def send_chat(orchestrator: "Orchestrator", request: "ChatSendRequest", emit, *, emit_event=None) -> dict:
    """Start one chat run and stream events through `emit` callback."""
    session_key = request.session_key.strip()
    message = request.message.strip()
    if not session_key:
        raise ValueError("session_key is required")
    if not message:
        raise ValueError("message is required")

    # Per Phase -1.2 (HARNESS_REBUILD_V2.md): use idempotency_key as run_id
    # when provided so callers (rpc_chat etc.) keep round-trip identity between
    # the chat.send response runId and the abort/trace key. Fall back to a
    # fresh UUID when no idempotency_key is supplied. The dedupe cache is
    # scoped per-session below to prevent cross-session bleed of cached
    # results (the original Codex peer-review finding).
    idempotency_key = request.idempotency_key.strip() if request.idempotency_key else ""
    run_id = idempotency_key or str(uuid4())
    provider_name = request.provider.strip() or "codex-cli"
    if provider_name not in orchestrator._providers:
        init_error = orchestrator._provider_init_errors.get(provider_name)
        if init_error:
            raise RuntimeError(f"provider unavailable: {provider_name} ({init_error})")
        raise ValueError(f"unsupported provider: {provider_name}")

    dedupe_key = f"chat:{session_key}:{idempotency_key}" if idempotency_key else None
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
        if dedupe_key is not None:
            cached = orchestrator._idempotency_cache.get(dedupe_key)
            if cached is not None:
                return {"runId": run_id, "status": "cached", "cached": True, "result": cached}

        active_run = orchestrator._active_run_by_session.get(session_key)
        if active_run and active_run != run_id:
            from . import SessionInFlightError

            raise SessionInFlightError(active_run)

        persona_context = orchestrator._persona_service.build_prompt_context(
            provider=provider_name,
            model=request.model,
            privacy_tier=request.persona_privacy_tier,
            query=message,
        )
        resolved_persona_id = request.persona_id or persona_context.persona_id
        resolved_persona_flavor_id = request.persona_flavor_id or persona_context.flavor_id
        resolved_persona_privacy_tier = request.persona_privacy_tier or persona_context.privacy_tier

        entry = orchestrator._session_store.resolve_or_create(
            session_key=session_key,
            provider=provider_name,
            model=request.model,
            system_prompt_id=request.system_prompt_id,
            task_prompt_id=request.task_prompt_id,
            persona_id=resolved_persona_id,
            persona_flavor_id=resolved_persona_flavor_id,
            persona_privacy_tier=resolved_persona_privacy_tier,
            workspace_root=orchestrator.validate_workspace_root(request.workspace_root) if request.workspace_root else None,
        )
        entry = orchestrator._session_store.assert_session_binding(
            session_key=session_key,
            provider=provider_name,
            model=request.model,
            system_prompt_id=request.system_prompt_id,
            task_prompt_id=request.task_prompt_id,
            persona_id=resolved_persona_id,
            persona_flavor_id=resolved_persona_flavor_id,
            persona_privacy_tier=resolved_persona_privacy_tier,
            workspace_root=entry.workspace_root or request.workspace_root,
        )
        session_workspace_root = (
            Path(orchestrator.validate_workspace_root(entry.workspace_root))
            if entry.workspace_root
            else orchestrator._workdir
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
            "workdir": str(session_workspace_root),
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
    effective_system_prompt = request.system_prompt
    # Phase 1 (HARNESS_REBUILD_V2): real multi-turn message history. `chat_history`
    # is read BEFORE the current user message was appended above — wait, the user
    # message IS already appended. So drop the trailing user row and let
    # build_chat_messages re-append `message` as the live request. This produces a
    # proper Responses messages[] array (used directly by the Phase 2 native loop)
    # and a clean flattened prompt for prompt-only providers (CLI / LM Studio).
    full_history = orchestrator.history(session_key=session_key, limit=400)
    history_for_replay = _history_excluding_current(full_history, run_id=run_id)
    chat_messages = build_chat_messages(
        transcript_messages=history_for_replay,
        current_user_message=message,
    )
    # CLI providers (claude-cli / codex-cli) keep their OWN conversation thread
    # server-side and resume it via provider_session_id. Re-sending the full
    # flattened transcript to a resuming CLI would double its context, so when we
    # can resume we send only the new user message. Everyone else (Responses path,
    # LM Studio, Ollama, or a CLI with no session to resume) gets the full
    # multi-turn replay.
    cli_resume = provider_name in _RESUME_CLI_PROVIDERS and bool(entry.provider_session_id)
    chat_prompt = message if cli_resume else flatten_messages_to_prompt(chat_messages)
    input_token_estimate = estimate_input_tokens(chat_messages)
    message_count = len(chat_messages)
    trace.record(
        "chat_messages_built",
        {
            "messageCount": message_count,
            "inputTokenEstimate": input_token_estimate,
            "historyTurns": len(history_for_replay),
            "cliResume": cli_resume,
        },
    )

    provider = orchestrator._providers[provider_name]
    seq = 0
    assistant_parts: list[str] = []
    assistant_message_parts: list[dict] = []
    tool_execution_payload: dict | None = None
    latest_turn_state: dict = {}
    normalized_tool_results: list[dict] = []
    artifact_drafts: list[dict] = []
    tool_steps: list[dict] = []
    persisted_tool_artifact_ids: list[str] = []
    identity_context_payload: dict[str, object] = {
        "profileActive": False,
        "memoryCount": 0,
        "memoryItemIds": [],
        "personaActive": False,
        "personaId": entry.persona_id,
        "personaFlavorId": entry.persona_flavor_id,
        "personaPrivacyTier": entry.persona_privacy_tier,
    }
    agent_runtime_payload = _build_agent_runtime_payload(
        session_key=session_key,
        task_prompt_id=entry.task_prompt_id or request.task_prompt_id,
        session_state=session_state,
    )
    effective_tool_policy = policy_for_task_mode(entry.task_prompt_id or request.task_prompt_id)
    available_tools = [
        tool
        for tool in orchestrator._tool_registry.list_tools()
        if tool.category in effective_tool_policy.allowed_categories
    ] if request.allow_tools else []
    try:
        plan, event_stream = await orchestrator._harness.run_turn(
            provider=provider,
            prompt=chat_prompt,
            messages=chat_messages,
            session_id=session_key,
            provider_session_id=entry.provider_session_id,
            abort_event=abort_event,
            model=request.model,
            system_prompt=effective_system_prompt,
            available_tools=available_tools,
            tool_executor=orchestrator._tool_registry.execute,
            tool_context=ToolExecutionContext(
                workdir=session_workspace_root,
                session_workspace_root=session_workspace_root,
                session_key=session_key,
                provider_name=provider_name,
                model=request.model,
                session_store=orchestrator._session_store,
                transcript_store=orchestrator._transcript_store,
                providers=orchestrator._providers,
                policy=effective_tool_policy,
                available_tools=available_tools,
                memory_service=orchestrator._memory_service,
                profile_service=orchestrator._profile_service,
                workspace_intel_service=orchestrator._workspace_intel_service,
                artifact_store=orchestrator._artifact_store,
                task_prompt_id=entry.task_prompt_id or request.task_prompt_id,
                run_id=run_id,
                trace=trace.record,
            ),
            trace=trace.record,
            prompt_context_builder=lambda resolved_plan: _build_identity_memory_overlay(
                orchestrator=orchestrator,
                plan=resolved_plan,
                query=message,
                provider=provider_name,
                model=request.model,
                persona_id=entry.persona_id,
                persona_flavor_id=entry.persona_flavor_id,
                persona_privacy_tier=entry.persona_privacy_tier,
                sink=identity_context_payload,
            ),
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

            if event.kind == "reasoning_delta" and event.text:
                # Phase 2: native reasoning summary deltas. Captured as a
                # "thinking" part + streamed over WS so the Phase 4 chat UX can
                # render inline thinking. Not folded into assistant_text.
                _append_thinking_part(assistant_message_parts, event.text)
                trace.record("reasoning_delta", {"chars": len(event.text)})
                seq += 1
                await emit(
                    {
                        "runId": run_id,
                        "sessionKey": session_key,
                        "seq": seq,
                        "state": "reasoning_delta",
                        "provider": provider_name,
                        "model": request.model,
                        "text": event.text,
                    }
                )

            if event.kind == "meta" and isinstance(event.metadata, dict):
                tool_call_payload = event.metadata.get("toolCall")
                if isinstance(tool_call_payload, dict):
                    assistant_message_parts.append({"kind": "tool_call", "toolCall": dict(tool_call_payload)})
                    seq += 1
                    await emit(
                        {
                            "runId": run_id,
                            "sessionKey": session_key,
                            "seq": seq,
                            "state": "tool_called",
                            "provider": provider_name,
                            "model": request.model,
                            "toolCall": dict(tool_call_payload),
                            "turnState": event.metadata.get("turnState") if isinstance(event.metadata.get("turnState"), dict) else None,
                        }
                    )
                tool_payload = event.metadata.get("toolExecution")
                if isinstance(tool_payload, dict):
                    tool_execution_payload = tool_payload
                    # Persist the actual tool output (not just the summary/preview)
                    # onto the transcript part so cross-turn replay re-feeds the
                    # model what it saw — otherwise multi-turn coding loses every
                    # file it read. The body is already bounded by the artifact
                    # mechanism (>4KB becomes an artifact preview dict).
                    stored_execution = dict(tool_payload)
                    replay_output = _replay_output_from_runtime_input(event.metadata.get("toolResult"))
                    if replay_output:
                        stored_execution["replayOutput"] = replay_output
                    assistant_message_parts.append({"kind": "tool_result", "toolExecution": stored_execution})
                    tool_steps.append(_normalize_tool_step(tool_payload))
                    artifact_id = str(tool_payload.get("artifactId") or "").strip()
                    if artifact_id and artifact_id not in persisted_tool_artifact_ids:
                        persisted_tool_artifact_ids.append(artifact_id)
                    seq += 1
                    await emit(
                        {
                            "runId": run_id,
                            "sessionKey": session_key,
                            "seq": seq,
                            "state": "tool_result",
                            "provider": provider_name,
                            "model": request.model,
                            "toolExecution": dict(tool_payload),
                            "turnState": event.metadata.get("turnState") if isinstance(event.metadata.get("turnState"), dict) else None,
                        }
                    )
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
                _append_text_part(assistant_message_parts, event.text)
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
                            "parts": [dict(part) for part in assistant_message_parts],
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
        assistant_message_parts = _normalize_final_message_parts(
            assistant_message_parts,
            assistant_text=assistant_text,
        )
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
        # Answer artifact only if there's final text to enshrine.
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

        # Transcript append runs whenever the run produced ANY assistant activity —
        # text, tool calls, or tool results. Without this, max-step / tool-only
        # turns vanish from transcript and Phase 1 message-history replay loses
        # their structured parts. (Fix per Codex peer review, PASS-7 followup.)
        if assistant_text or assistant_message_parts:
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
                    state="final" if assistant_text else "tool_only",
                    tool_execution=tool_execution_payload,
                    parts=[dict(part) for part in assistant_message_parts] if assistant_message_parts else None,
                ),
            )
            trace.record(
                "assistant_finalized",
                {
                    "responseLength": len(assistant_text),
                    "toolExecutionAttached": bool(tool_execution_payload),
                    "partsCount": len(assistant_message_parts) if assistant_message_parts else 0,
                    "toolOnly": bool(not assistant_text and assistant_message_parts),
                },
            )

        # Title generation only if first-turn AND we have final text to title from.
        if assistant_text and is_first_turn and not (entry.title or "").strip():
            orchestrator._schedule_title_generation(
                session_key=session_key,
                provider_name=provider_name,
                model=request.model,
                first_user_message=message,
                first_assistant_message=assistant_text,
            )

        updated_state = _evolve_session_state(
            session_state=session_state,
            run_id=run_id,
            plan=plan,
            task_prompt_id=entry.task_prompt_id or request.task_prompt_id,
            created_artifact_ids=created_artifact_ids,
        )
        orchestrator._session_state_store.save(updated_state)
        trace.record(
            "state_updated",
            {
                "sessionKey": session_key,
                "relevantArtifactCount": len(updated_state.relevant_artifact_ids),
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
            working_set={},
            message_count=message_count,
            input_token_estimate=input_token_estimate,
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
                **agent_runtime_payload,
                "delegatedTasks": list(agent_runtime_payload.get("delegatedTasks") or []),
                "toolManifest": describe_available_tools(plan.tools),
                "toolVisibility": _build_tool_visibility_summary(plan.tools),
                "harnessDecision": dict(plan.harness_decision),
                "policySummary": {
                    "allowedCategories": sorted(effective_tool_policy.allowed_categories),
                    "shellAllowlist": list(effective_tool_policy.shell_allowlist),
                },
                "workspaceRoot": str(session_workspace_root),
                "turnState": dict(latest_turn_state),
                "identityContext": dict(identity_context_payload),
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
        # Phase 0.4: auto-extraction is OFF by default. The previous behavior
        # keyword-scraped user text for "i like / do not / we should" and
        # re-injected those into next-turn prompts, polluting context. Enable
        # via COPNET_AUTO_PROFILE_EXTRACTION / COPNET_AUTO_MEMORY_EXTRACTION.
        profile_changes = []
        if auto_profile_extraction_enabled():
            try:
                profile_changes = orchestrator._profile_service.apply_post_run_updates(
                    user_message=message,
                    run_record=run_record,
                )
            except Exception as exc:
                trace.record("post_run_side_effect_failed", {"stage": "profile", "error": str(exc)})
        else:
            trace.record("post_run_side_effect_skipped", {"stage": "profile", "reason": "auto_extraction_disabled"})
        memory_created = []
        if auto_memory_extraction_enabled():
            try:
                memory_changes = orchestrator._memory_service.extract_from_run(
                    user_message=message,
                    run_record=run_record,
                )
                memory_created = list(memory_changes.created)
            except Exception as exc:
                trace.record("post_run_side_effect_failed", {"stage": "memory", "error": str(exc)})
        else:
            trace.record("post_run_side_effect_skipped", {"stage": "memory", "reason": "auto_extraction_disabled"})
        if memory_created:
            trace.record(
                "memory_extracted",
                {
                    "count": len(memory_created),
                    "itemIds": [item.id for item in memory_created],
                    "categories": [item.category for item in memory_created],
                },
            )
        if emit_event is not None and profile_changes:
            try:
                profile_payload = orchestrator.get_pat_profile()
                for item in profile_changes:
                    await emit_event(
                        "profile.changed",
                        {
                            "profile": profile_payload,
                            "change": item.to_json(),
                        },
                    )
            except Exception as exc:
                trace.record("post_run_side_effect_failed", {"stage": "profile_emit", "error": str(exc)})
        if emit_event is not None and memory_created:
            try:
                for item in memory_created:
                    await emit_event(
                        "memory.changed",
                        {
                            "item": item.to_public_dict(),
                            "reason": "run_extraction",
                            "sessionKey": session_key,
                            "runId": run_id,
                        },
                    )
            except Exception as exc:
                trace.record("post_run_side_effect_failed", {"stage": "memory_emit", "error": str(exc)})
        try:
            briefing_payload = orchestrator.get_return_briefing()
            if emit_event is not None and briefing_payload is not None:
                await emit_event("briefing.ready", {"briefing": briefing_payload})
        except Exception as exc:
            trace.record("post_run_side_effect_failed", {"stage": "briefing", "error": str(exc)})

        seq += 1
        final_payload = {
            "runId": run_id,
            "sessionKey": session_key,
            "seq": seq,
            "state": "final",
            "message": {
                "role": "assistant",
                "content": assistant_text,
                "parts": [dict(part) for part in assistant_message_parts],
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
            "harnessDecision": dict(plan.harness_decision),
            "identityContext": identity_context_payload,
            "agentContext": agent_runtime_payload,
        }
        await emit(final_payload)
        trace.record(
            "run_completed",
            {
                "status": "ok",
                "toolExecutionAttached": bool(tool_execution_payload),
            },
        )
        if dedupe_key is not None:
            async with orchestrator._lock:
                orchestrator._idempotency_cache[dedupe_key] = final_payload
        return {"runId": run_id, "status": "ok"}
    except Exception as exc:
        import traceback as _tb
        tb_text = _tb.format_exc()
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
            working_set={},
            message_count=message_count if "message_count" in locals() else 0,
            input_token_estimate=input_token_estimate if "input_token_estimate" in locals() else 0,
            tool_steps=tool_steps,
            artifact_ids=list(persisted_tool_artifact_ids),
            output_summary="",
            error=str(exc),
            transition_reason=str(latest_turn_state.get("transitionReason") or "model_error"),
            terminal_reason="model_error",
            tool_results=normalized_tool_results,
            pending_input_count=int(latest_turn_state.get("pendingInputCount") or 0),
            oversized_tool_artifact_ids=list(persisted_tool_artifact_ids),
            metadata=(
                {
                    "workspaceRoot": str(session_workspace_root),
                    "harnessDecision": dict(plan.harness_decision),
                    **agent_runtime_payload,
                }
                if "session_workspace_root" in locals() and "plan" in locals()
                else ({"workspaceRoot": str(session_workspace_root)} if "session_workspace_root" in locals() else {})
            ),
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
                "errorType": exc.__class__.__name__,
                "traceback": tb_text,
            },
        )
        if dedupe_key is not None:
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
    run_id: str,
    plan,
    task_prompt_id: str | None,
    created_artifact_ids: list[str],
) -> SessionStateRecord:
    """Update durable session state after a run.

    Phase 1 (HARNESS_REBUILD_V2) killed the keyword auto-mutation that used to
    synthesize task_summary / goals / active_entities / unresolved_questions /
    prior_decisions / topical_tags from conversation text. The transcript IS the
    context now (replayed via build_chat_messages), so we only track concrete
    artifact references plus a plan snapshot for the inspector.

    The remaining SessionStateRecord text fields are preserved as-is (not
    narrowed away yet) so Pulse / Merge — which still read and write them and
    are scheduled for a later rewire per the plan's deferral list — keep working
    and degrade gracefully rather than crashing on a removed attribute.
    """
    relevant_artifact_ids = _append_unique(
        session_state.relevant_artifact_ids,
        created_artifact_ids,
    )[-10:]
    agent_runtime = _build_agent_runtime_payload(
        session_key=session_state.session_key,
        task_prompt_id=task_prompt_id,
        session_state=session_state,
    )
    return SessionStateRecord(
        session_key=session_state.session_key,
        task_summary=session_state.task_summary,
        goals=list(session_state.goals),
        active_entities=list(session_state.active_entities),
        working_set_refs=list(session_state.working_set_refs),
        constraints=list(session_state.constraints),
        unresolved_questions=list(session_state.unresolved_questions),
        prior_decisions=list(session_state.prior_decisions),
        starter_intent=session_state.starter_intent,
        topical_tags=list(session_state.topical_tags),
        plan_snapshot={
            "runId": run_id,
            "toolExecutionMode": plan.tool_execution_mode,
            "willAttemptToolLoop": plan.will_attempt_tool_loop,
            "taskPromptId": task_prompt_id,
            **agent_runtime,
            "toolManifest": describe_available_tools(plan.tools),
        },
        relevant_asset_ids=list(session_state.relevant_asset_ids),
        relevant_artifact_ids=relevant_artifact_ids,
        merge_state=dict(session_state.merge_state),
        pulse_state=dict(session_state.pulse_state),
        created_at=session_state.created_at,
        updated_at=transcript_now(),
    )


def _history_excluding_current(history: list[dict], *, run_id: str) -> list[dict]:
    """Return transcript history with the just-appended current user row removed.

    send_chat appends the user message to the transcript before building the
    replay array. build_chat_messages re-appends the live message itself, so we
    strip the trailing user row for this run_id to avoid duplicating it.
    """
    if not history:
        return []
    trimmed = list(history)
    last = trimmed[-1]
    if last.get("role") == "user" and str(last.get("runId") or last.get("run_id") or "") == run_id:
        trimmed = trimmed[:-1]
    return trimmed


def _append_unique(existing: list[str], incoming: list[str]) -> list[str]:
    rows = list(existing)
    for item in incoming:
        text = str(item).strip()
        if text and text not in rows:
            rows.append(text)
    return rows


def _append_text_part(parts: list[dict], text: str) -> None:
    if not text:
        return
    if parts and parts[-1].get("kind") == "text":
        parts[-1]["text"] = f"{parts[-1].get('text') or ''}{text}"
        return
    parts.append({"kind": "text", "text": text})


def _replay_output_from_runtime_input(runtime_input: object) -> str:
    """Extract the model-facing tool output string from a tool's runtime input.

    Used to persist `replayOutput` on the transcript tool_result part so a later
    turn replays the real output (file contents, command stdout, ...) rather than
    just the one-line summary. Bounded already by the artifact mechanism.
    """
    if not isinstance(runtime_input, dict):
        return ""
    body = runtime_input.get("body")
    if isinstance(body, str):
        return body
    if isinstance(body, (dict, list)):
        try:
            return json.dumps(body, ensure_ascii=False, indent=2)
        except (TypeError, ValueError):
            return str(body)
    summary = runtime_input.get("summary")
    return str(summary) if isinstance(summary, str) else ""


def _append_thinking_part(parts: list[dict], text: str) -> None:
    if not text:
        return
    if parts and parts[-1].get("kind") == "thinking":
        parts[-1]["text"] = f"{parts[-1].get('text') or ''}{text}"
        return
    parts.append({"kind": "thinking", "text": text})


def _normalize_final_message_parts(parts: list[dict], *, assistant_text: str) -> list[dict]:
    if not assistant_text:
        return [dict(part) for part in parts]
    non_text_parts = [dict(part) for part in parts if part.get("kind") != "text"]
    if not non_text_parts:
        return [{"kind": "text", "text": assistant_text}]
    normalized: list[dict] = []
    inserted_text = False
    for part in parts:
        if part.get("kind") == "text":
            if inserted_text:
                continue
            normalized.append({"kind": "text", "text": assistant_text})
            inserted_text = True
            continue
        normalized.append(dict(part))
    if not inserted_text:
        normalized.insert(0, {"kind": "text", "text": assistant_text})
    return normalized


def _build_tool_visibility_summary(tools: list[Any]) -> dict[str, list[str]]:
    visible = [str(tool.id) for tool in tools]
    auto_allowed = [str(tool.id) for tool in tools if getattr(tool, "manifest_permission", lambda: "")() == "auto_allowed"]
    policy_gated = [str(tool.id) for tool in tools if getattr(tool, "manifest_permission", lambda: "")() == "policy_gated"]
    return {
        "visibleToolIds": visible,
        "autoAllowedToolIds": auto_allowed,
        "policyGatedToolIds": policy_gated,
    }


def _build_agent_runtime_payload(
    *,
    session_key: str,
    task_prompt_id: str | None,
    session_state: SessionStateRecord,
) -> dict[str, object]:
    raw_tasks = session_state.plan_snapshot.get("delegatedTasks") if isinstance(session_state.plan_snapshot, dict) else []
    delegated_tasks = [dict(item) for item in raw_tasks] if isinstance(raw_tasks, list) else []
    permission_mode = "workspace_write" if (task_prompt_id or "").strip().lower() == "full-access" else "read_only"
    return {
        "agentId": f"lead:{session_key}",
        "parentAgentId": None,
        "agentRole": "lead",
        "permissionMode": permission_mode,
        "planModeRequired": False,
        "delegatedTasks": delegated_tasks,
    }


def _normalize_tool_step(tool_payload: dict) -> dict:
    members: list[dict] = []
    raw_members = tool_payload.get("members")
    if isinstance(raw_members, list):
        for item in raw_members:
            if not isinstance(item, dict):
                continue
            member: dict[str, object] = {
                "toolId": str(item.get("toolId") or "").strip(),
                "ok": bool(item.get("ok")),
                "summary": str(item.get("summary") or ""),
                "error": str(item.get("error")).strip() if item.get("error") is not None else None,
            }
            for key in ("callId", "artifactId", "target", "workspaceRoot", "scope", "accessAction", "policyDecision", "policySummary"):
                value = item.get(key)
                if value is not None:
                    member[key] = value
            preview = item.get("preview")
            if isinstance(preview, dict):
                member["preview"] = dict(preview)
            members.append(member)
    return {
        "callId": str(tool_payload.get("callId") or "").strip() or None,
        "toolId": str(tool_payload.get("toolId") or "").strip(),
        "channel": str(tool_payload.get("channel") or "tool").strip(),
        "ok": bool(tool_payload.get("ok")),
        "summary": str(tool_payload.get("summary") or ""),
        "error": str(tool_payload.get("error")).strip() if tool_payload.get("error") is not None else None,
        "artifactId": str(tool_payload.get("artifactId") or "").strip() or None,
        "target": str(tool_payload.get("target") or "").strip() or None,
        "workspaceRoot": str(tool_payload.get("workspaceRoot") or "").strip() or None,
        "scope": str(tool_payload.get("scope") or "").strip() or None,
        "accessAction": str(tool_payload.get("accessAction") or "").strip() or None,
        "policyDecision": str(tool_payload.get("policyDecision") or "").strip() or None,
        "policySummary": str(tool_payload.get("policySummary") or "").strip() or None,
        "status": "blocked" if tool_payload.get("ok") is False else "ok",
        "batched": str(tool_payload.get("channel") or "") == "batch" or str(tool_payload.get("toolId") or "") == "tool.batch",
        "members": members,
    }


def _summarize_output(text: str) -> str:
    return " ".join(text.split())[:240]


def _build_identity_memory_overlay(
    *,
    orchestrator: "Orchestrator",
    plan,
    query: str,
    provider: str,
    model: str | None,
    persona_id: str | None,
    persona_flavor_id: str | None,
    persona_privacy_tier: str | None,
    sink: dict[str, object],
) -> str | None:
    persona_payload = orchestrator._persona_service.build_prompt_context(
        provider=provider,
        model=model,
        privacy_tier=persona_privacy_tier,  # type: ignore[arg-type]
        query=query,
    )
    identity_payload = orchestrator._profile_service.build_identity_prompt_payload(
        include_briefing=plan.will_attempt_tool_loop
    )
    memory_payload = orchestrator._memory_service.build_prompt_payload(
        query=query,
        limit=3 if plan.will_attempt_tool_loop else 1,
    )
    sink["profileActive"] = bool(identity_payload.stable_identity)
    sink["memoryCount"] = len(memory_payload.memory_items)
    sink["memoryItemIds"] = [item.id for item in memory_payload.memory_items]
    sink["personaActive"] = bool(persona_payload.prompt)
    sink["personaId"] = persona_id or persona_payload.persona_id
    sink["personaFlavorId"] = persona_flavor_id or persona_payload.flavor_id
    sink["personaPrivacyTier"] = persona_privacy_tier or persona_payload.privacy_tier
    parts = [
        part
        for part in (
            persona_payload.prompt,
            identity_payload.stable_identity,
            identity_payload.situational_briefing,
            memory_payload.digest,
        )
        if part
    ]
    return "\n\n".join(parts) if parts else None
