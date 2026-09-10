"""Prepare the current turn, tools and bounded replay input."""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from . import Orchestrator


from copenet.core.harness.responses_items import image_content_part
from copenet.core.orchestrator.market_context import (
    chart_prompt_policy,
    current_chart_message,
    chart_system_overlay,
)
from copenet.core.orchestrator.context_budget import discover_model_context_tokens, resolve_context_budget
from copenet.core.orchestrator.messages import (
    build_chat_messages,
    estimate_input_tokens,
    flatten_messages_to_prompt,
)
from copenet.core.harness.context_window import estimate_request_tokens, trim_messages_to_request_budget
from copenet.core.orchestrator.tool_requests import (
    append_system_overlay,
    requested_tool_overlay,
)
from copenet.core.sessions import TranscriptMessage
from copenet.core.sessions.transcript_store import utc_now_iso as transcript_now
from copenet.core.tools import (
    build_responses_tool_schemas,
)
from copenet.prompts import (
    compose_prompt,
)

from .run_types import RunAdmission, RunInput
from .run_tools import select_run_tools
from .run_state import _build_agent_runtime_payload

# Providers that maintain their own conversation thread and resume it via
# provider_session_id — they must NOT be re-fed the flattened transcript.
_RESUME_CLI_PROVIDERS = {"claude-cli"}
_MAX_TOOL_LOOP_RESERVE_TOKENS = 25_000


def _tool_loop_reserve(input_tokens: int, has_tools: bool) -> int:
    if not has_tools:
        return 0
    return min(_MAX_TOOL_LOOP_RESERVE_TOKENS, max(4_000, input_tokens // 5))


def resolve_attachment_images(attachment_store, refs: list[dict]) -> list[dict]:
    """Re-inline images for a past user turn from its persisted attachment refs."""
    parts: list[dict] = []
    for ref in refs:
        ref_id = str(ref.get("attachmentId") or "").strip()
        if not ref_id:
            continue
        data_url = attachment_store.data_url(ref_id)
        if data_url:
            parts.append(image_content_part(data_url))
    return parts


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


async def prepare_run_input(orchestrator: "Orchestrator", admission: RunAdmission):
    tools = select_run_tools(orchestrator, admission)
    orchestrator._transcript_store.append_message(
        admission.entry.session_id,
        TranscriptMessage(
            run_id=admission.run_id,
            role="user",
            content=admission.message,
            provider=admission.provider_name,
            model=admission.request.model,
            provider_session_id=admission.entry.provider_session_id,
            timestamp=transcript_now(),
            attachments=admission.attachment_refs or None,
            requested_tool_ids=list(tools.requested_tool_ids) or None,
            market_context=admission.market_reference,
        ),
    )
    session_state = orchestrator._session_state_store.get_or_create(admission.session_key)
    admission.trace.record(
        "state_loaded",
        {
            "sessionKey": admission.session_key,
            "relevantArtifactCount": len(session_state.relevant_artifact_ids),
            "relevantAssetCount": len(session_state.relevant_asset_ids),
            "workingSetRefCount": len(session_state.working_set_refs),
        },
    )
    resolved_system_prompt_id = admission.entry.system_prompt_id or admission.request.system_prompt_id
    resolved_task_prompt_id = admission.entry.task_prompt_id or admission.request.task_prompt_id
    composed_system_prompt = compose_prompt(resolved_system_prompt_id, resolved_task_prompt_id)
    effective_system_prompt = append_system_overlay(
        admission.request.system_prompt or composed_system_prompt,
        requested_tool_overlay(tools.active_requested_tool_ids),
    )
    effective_system_prompt = append_system_overlay(
        effective_system_prompt, chart_system_overlay(admission.market_context)
    )
    prompt_policy = chart_prompt_policy(admission.market_context, resolved_system_prompt_id)
    admission.trace.record(
        "prompt_context_policy_resolved",
        {
            "purpose": prompt_policy.purpose.value,
            "systemPromptId": resolved_system_prompt_id,
            "taskPromptId": resolved_task_prompt_id,
            "systemPromptSource": "request_override" if admission.request.system_prompt else "composed",
            "baseSystemPromptChars": len(effective_system_prompt or ""),
            "requestedToolIds": list(tools.requested_tool_ids),
            "activeRequestedToolIds": list(tools.active_requested_tool_ids),
            "rejectedRequestedToolIds": list(tools.rejected_requested_tool_ids),
            "includePersonaContext": prompt_policy.include_persona_context,
            "includePersonaAgentInstructions": prompt_policy.include_persona_agent_instructions,
            "includeRelevantMemory": prompt_policy.include_relevant_memory,
        },
    )
    full_history = orchestrator.history(session_key=admission.session_key, limit=400)
    history_for_replay = _history_excluding_current(full_history, run_id=admission.run_id)
    provider = orchestrator._providers[admission.provider_name]
    declared_context_tokens = await discover_model_context_tokens(provider, admission.request.model)
    context_budget = resolve_context_budget(
        provider=admission.provider_name, model_context_tokens=declared_context_tokens
    )
    tool_schemas = build_responses_tool_schemas(tools.available_tools)
    fixed_input_tokens = estimate_request_tokens([], instructions=effective_system_prompt, tools=tool_schemas)
    loop_reserve_tokens = _tool_loop_reserve(context_budget.input_tokens, bool(tools.available_tools))
    initial_input_budget = context_budget.input_tokens - loop_reserve_tokens
    live_without_chart = build_chat_messages(
        transcript_messages=[],
        current_user_message=admission.message,
        current_user_image_parts=admission.current_image_parts or None,
    )
    chart_token_limit = max(
        initial_input_budget - fixed_input_tokens - estimate_input_tokens(live_without_chart), 1
    )
    current_message = current_chart_message(
        orchestrator, admission.message, admission.market_context, token_limit=chart_token_limit
    )
    unbounded_chat_messages = build_chat_messages(
        transcript_messages=history_for_replay,
        current_user_message=current_message,
        current_user_image_parts=admission.current_image_parts or None,
        attachment_resolver=lambda refs: resolve_attachment_images(orchestrator._chat_attachment_store, refs),
    )
    unbounded_token_estimate = estimate_input_tokens(unbounded_chat_messages)
    chat_messages = trim_messages_to_request_budget(
        unbounded_chat_messages,
        max_input_tokens=initial_input_budget,
        instructions=effective_system_prompt,
        tools=tool_schemas,
    )
    cli_resume = admission.provider_name in _RESUME_CLI_PROVIDERS and bool(
        admission.entry.provider_session_id
    )
    chat_prompt = current_message if cli_resume else flatten_messages_to_prompt(chat_messages)
    input_token_estimate = estimate_input_tokens(chat_messages)
    preplan_input_token_estimate = estimate_request_tokens(
        chat_messages, instructions=effective_system_prompt, tools=tool_schemas
    )
    message_count = len(chat_messages)
    admission.trace.record(
        "chat_messages_built",
        {
            "messageCount": message_count,
            "inputTokenEstimate": input_token_estimate,
            "prePlanInputTokenEstimate": preplan_input_token_estimate,
            "unboundedInputTokenEstimate": unbounded_token_estimate,
            "fixedInputTokenEstimate": fixed_input_tokens,
            "initialInputTokenBudget": initial_input_budget,
            "toolLoopReserveTokens": loop_reserve_tokens,
            "chartInitialTokenLimit": chart_token_limit if admission.market_context is not None else None,
            "omittedMessageItemCount": len(unbounded_chat_messages) - len(chat_messages),
            "historyTurns": len(history_for_replay),
            "cliResume": cli_resume,
            **context_budget.to_trace_dict(),
        },
    )
    identity_context_payload: dict[str, object] = {
        "memoryCount": 0,
        "memoryItemIds": [],
        "personaActive": False,
        "personaId": admission.entry.persona_id,
        "personaFlavorId": admission.entry.persona_flavor_id,
        "personaPrivacyTier": admission.entry.persona_privacy_tier,
    }
    agent_runtime_payload = _build_agent_runtime_payload(
        session_key=admission.session_key,
        task_prompt_id=admission.entry.task_prompt_id or admission.request.task_prompt_id,
        session_state=session_state,
    )
    return RunInput(
        session_state=session_state,
        effective_system_prompt=effective_system_prompt,
        resolved_system_prompt_id=resolved_system_prompt_id,
        resolved_task_prompt_id=resolved_task_prompt_id,
        prompt_policy=prompt_policy,
        context_budget=context_budget,
        history_for_replay=history_for_replay,
        chat_messages=chat_messages,
        chat_prompt=chat_prompt,
        message_count=message_count,
        input_token_estimate=input_token_estimate,
        preplan_input_token_estimate=preplan_input_token_estimate,
        unbounded_token_estimate=unbounded_token_estimate,
        initial_input_budget=initial_input_budget,
        loop_reserve_tokens=loop_reserve_tokens,
        agent_runtime_payload=agent_runtime_payload,
        identity_context_payload=identity_context_payload,
        tools=tools,
    )
