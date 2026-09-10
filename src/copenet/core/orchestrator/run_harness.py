"""Bind prepared input to the harness and its scoped tool executor."""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from . import Orchestrator

from typing import Any

from copenet.core.orchestrator.market_context import (
    update_chart_admission,
    chart_store,
    prepare_chart_tool_context,
    create_chart_manifest,
)
from copenet.core.orchestrator.approval_execution import make_approval_gated_executor
from copenet.core.tools import (
    ToolExecutionContext,
)

from .run_types import RunAdmission, RunInput, RunEvents
from .run_identity import _build_identity_memory_overlay


async def start_harness(
    orchestrator: "Orchestrator", admission: RunAdmission, prepared: RunInput, events: RunEvents, emit_event
):
    model_input_snapshot: dict[str, Any] | None = {} if admission.trace.debug else None
    events.chart_manifest_id = create_chart_manifest(
        orchestrator, admission.market_context, admission.market_reference
    )
    update_chart_admission(orchestrator, admission.request, "dispatched")
    events.plan, event_stream = await orchestrator._harness.run_turn(
        provider=orchestrator._providers[admission.provider_name],
        prompt=prepared.chat_prompt,
        messages=prepared.chat_messages,
        session_id=admission.session_key,
        provider_session_id=admission.entry.provider_session_id,
        abort_event=admission.abort_event,
        model=admission.request.model,
        system_prompt=prepared.effective_system_prompt,
        purpose=prepared.prompt_policy.purpose.value,
        input_token_budget=prepared.context_budget.input_tokens,
        debug_snapshot=model_input_snapshot,
        available_tools=prepared.tools.available_tools,
        tool_executor=make_approval_gated_executor(
            orchestrator._tool_registry.execute,
            orchestrator=orchestrator,
            emit_event=emit_event,
            session_key=admission.session_key,
            run_id=admission.run_id,
            abort_event=admission.abort_event,
        ),
        tool_context=prepare_chart_tool_context(
            ToolExecutionContext(
                workdir=admission.session_workspace_root,
                session_workspace_root=admission.session_workspace_root,
                session_key=admission.session_key,
                provider_name=admission.provider_name,
                model=admission.request.model,
                session_store=orchestrator._session_store,
                transcript_store=orchestrator._transcript_store,
                providers=orchestrator._providers,
                policy=prepared.tools.effective_tool_policy,
                available_tools=prepared.tools.available_tools,
                memory_service=orchestrator._memory_service,
                workspace_intel_service=orchestrator._workspace_intel_service,
                persona_service=orchestrator._persona_service,
                user_notes_service=orchestrator._user_notes_service,
                artifact_store=orchestrator._artifact_store,
                edit_backup_store=orchestrator._edit_backup_store,
                permission_store=orchestrator._permission_store,
                task_prompt_id=admission.entry.task_prompt_id or admission.request.task_prompt_id,
                run_id=admission.run_id,
                trace=admission.trace.record,
                market_context=admission.market_context,
                chart_store=chart_store(orchestrator) if admission.market_context is not None else None,
                allowed_tool_ids=prepared.tools.scoped_tool_ids if admission.request.allow_tools else frozenset(),
                ephemeral={"chart_event_emit": emit_event}
                if admission.market_context is not None and emit_event is not None
                else {},
            ),
            orchestrator=orchestrator,
            market_context=admission.market_context,
            history=prepared.history_for_replay,
        ),
        trace=admission.trace.record,
        prompt_context_builder=lambda resolved_plan: _build_identity_memory_overlay(
            orchestrator=orchestrator,
            plan=resolved_plan,
            query=admission.message,
            provider=admission.provider_name,
            model=admission.request.model,
            persona_id=admission.entry.persona_id,
            persona_flavor_id=admission.entry.persona_flavor_id,
            persona_privacy_tier=admission.entry.persona_privacy_tier,
            policy=prepared.prompt_policy,
            sink=prepared.identity_context_payload,
        ),
    )
    if model_input_snapshot is not None:
        admission.trace.record_debug(
            "model_input_snapshot",
            {
                **model_input_snapshot,
                "promptContextPolicy": {
                    "purpose": prepared.prompt_policy.purpose.value,
                    "systemPromptId": prepared.resolved_system_prompt_id,
                    "taskPromptId": prepared.resolved_task_prompt_id,
                },
                "contextWindow": {
                    "messageCount": prepared.message_count,
                    "inputTokenEstimate": prepared.input_token_estimate,
                    "prePlanInputTokenEstimate": prepared.preplan_input_token_estimate,
                    "unboundedInputTokenEstimate": prepared.unbounded_token_estimate,
                    "initialInputTokenBudget": prepared.initial_input_budget,
                    "toolLoopReserveTokens": prepared.loop_reserve_tokens,
                },
            },
        )
    return (events.plan, event_stream)
