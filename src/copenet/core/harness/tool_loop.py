"""Provider execution helpers and native tool calling for the CopeNet harness."""

from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator, Awaitable, Callable, Protocol
from uuid import uuid4

from copenet.core.runtime import TurnState
from copenet.core.tools import (
    ToolDescriptor,
    ToolExecutionContext,
    ToolExecutionRequest,
    ToolExecutionResult,
    build_openai_tool_schemas,
    build_responses_tool_schemas,
)
from copenet.providers import Provider, ProviderEvent

from . import responses_items
from .planning import HarnessTurnPlan


class ResponsesProvider(Protocol):
    name: str

    def stream_responses(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        model: str | None,
        instructions: str | None,
        prompt_cache_key: str | None,
        reasoning: dict[str, Any] | None,
        parallel_tool_calls: bool,
        abort_event: asyncio.Event,
    ) -> AsyncIterator[ProviderEvent]:
        """Stream one Responses-API turn over a pre-built input[] array."""


ToolExecutor = Callable[[ToolExecutionRequest, ToolExecutionContext], Awaitable[ToolExecutionResult]]
TraceRecorder = Callable[[str, dict[str, Any] | None], None]
# Frontier harnesses leave step-count to the model. 100 is high enough that
# real work never hits it, low enough that runaway loops eventually stop.
MAX_TOOL_STEPS = 100
LARGE_TOOL_RESULT_CHAR_LIMIT = 4000

# Default reasoning config for the native Responses path. summary="auto" is what
# makes the endpoint stream reasoning_summary deltas — i.e. what powers the
# Phase 4 inline-thinking UX. Without this, no thinking ever renders.
# NOTE: verified shape per scripts/codex_responses_probe.py scenario C; needs a
# live run to confirm the endpoint accepts it for the active model.
DEFAULT_RESPONSES_REASONING: dict[str, Any] = {"effort": "medium", "summary": "auto"}


def _max_step_explanation() -> str:
    return (
        f"[Stopped after MAX_TOOL_STEPS={MAX_TOOL_STEPS} tool calls. "
        "Returning what was produced so far.]"
    )


class NativeToolProvider(Protocol):
    name: str

    async def chat_completion(
        self,
        *,
        messages: list[dict[str, Any]],
        model: str | None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Run one non-streaming native tool-capable chat completion."""


async def collect_provider_turn(
    *,
    provider: Provider,
    prompt: str,
    provider_session_id: str | None,
    abort_event: asyncio.Event,
    model: str | None,
    system_prompt: str | None,
    trace: TraceRecorder | None = None,
    phase: str = "provider",
) -> tuple[list[ProviderEvent], str | None]:
    """Collect one provider turn into memory for callers that need a buffered turn."""
    events: list[ProviderEvent] = []
    discovered = provider_session_id
    if trace is not None:
        trace("provider_turn_started", {"phase": phase, "providerSessionId": provider_session_id})
    async for event in provider.run(
        prompt=compose_provider_prompt(provider, prompt, system_prompt),
        provider_session_id=provider_session_id,
        abort_event=abort_event,
        model=model,
        system_prompt=provider_system_prompt(provider, system_prompt),
    ):
        if event.provider_session_id:
            discovered = event.provider_session_id
        events.append(event)
        if event.kind == "final":
            break
    if trace is not None:
        trace(
            "provider_turn_completed",
            {
                "phase": phase,
                "providerSessionId": discovered,
                "deltaCount": sum(1 for event in events if event.kind == "delta"),
            },
        )
    return events, discovered


async def run_with_native_tools(
    *,
    provider: NativeToolProvider,
    prompt: str,
    provider_session_id: str | None,
    abort_event: asyncio.Event,
    model: str | None,
    system_prompt: str | None,
    plan: HarnessTurnPlan,
    tool_executor: ToolExecutor,
    tool_context: ToolExecutionContext,
    trace: TraceRecorder | None,
) -> AsyncIterator[ProviderEvent]:
    """Run an OpenAI-compatible native tool loop without parsing final text."""
    del abort_event
    turn_state = TurnState(turn_id=plan.turn_id, decision_id=plan.decision_id)
    tool_schemas = build_openai_tool_schemas(plan.tools)
    current_system_prompt = compose_native_tool_system_prompt(
        provider=provider,
        system_prompt=system_prompt,
    )
    messages: list[dict[str, Any]] = []
    if current_system_prompt:
        messages.append({"role": "system", "content": current_system_prompt})
    messages.append({"role": "user", "content": prompt})
    latest_content = ""
    if trace is not None:
        trace("turn_started", turn_state.to_public_dict())

    for step_index in range(MAX_TOOL_STEPS):
        response = await provider.chat_completion(
            messages=messages,
            model=model,
            tools=tool_schemas or None,
        )
        message, finish_reason = _extract_native_choice(response)
        content = _coerce_native_message_content(message.get("content"))
        if content:
            latest_content = content
        native_tool_calls = _extract_native_tool_calls(message.get("tool_calls"))
        if trace is not None:
            trace(
                "provider_response_interpreted",
                {
                    "phase": "native",
                    "responseKind": "native_tool_call" if native_tool_calls else "native_final",
                    "toolCallCount": len(native_tool_calls),
                    "contentLength": len(content),
                    "finishReason": finish_reason,
                },
            )

        if not native_tool_calls:
            turn_state.terminal_reason = "completed"
            if trace is not None:
                trace("turn_completed", turn_state.to_public_dict())
            if content:
                yield ProviderEvent(kind="delta", text=content, provider_session_id=provider_session_id)
            yield ProviderEvent(kind="final", provider_session_id=provider_session_id)
            return

        assistant_message: dict[str, Any] = {"role": "assistant", "tool_calls": native_tool_calls}
        if content:
            assistant_message["content"] = content
        messages.append(assistant_message)
        for native_call in native_tool_calls:
            tool_id = native_call["function"]["name"]
            arguments = _parse_native_tool_arguments(native_call["function"].get("arguments"))
            request = ToolExecutionRequest(tool_id=tool_id, arguments=arguments)
            call_id = str(native_call.get("id") or "").strip() or _new_call_id(request.tool_id)
            if trace is not None:
                trace(
                    "tool_requested",
                    {
                        "toolId": request.tool_id,
                        "arguments": request.arguments,
                        "step": step_index + 1,
                        "native": True,
                        "callId": call_id,
                    },
                )
            yield ProviderEvent(
                kind="meta",
                metadata={
                    "toolCall": _tool_call_event_payload(
                        tool_id=request.tool_id,
                        arguments=request.arguments,
                        step=step_index + 1,
                        turn_id=plan.turn_id,
                        decision_id=plan.decision_id,
                        native=True,
                        call_id=call_id,
                    ),
                    "turnState": turn_state.to_public_dict(),
                },
            )
            tool_result = await tool_executor(request, tool_context)
            tool_result = _force_call_id(tool_result, call_id)
            tool_result, artifact_draft = _materialize_tool_result_artifact(
                tool_result=tool_result,
                tool_context=tool_context,
                trace=trace,
            )
            turn_state.tool_call_count += 1
            turn_state.record_tool_step(
                tool_id=tool_result.tool_id,
                arguments=request.arguments,
                result=tool_result,
            )
            turn_state.queue_input(tool_result.to_runtime_input(), reason="tool_followup")
            meta_payload: dict[str, Any] = {
                "toolExecution": _tool_result_event_payload(
                    result=tool_result,
                    request=request,
                    plan=plan,
                ),
                "toolResult": tool_result.to_runtime_input(),
                "turnState": turn_state.to_public_dict(),
            }
            if artifact_draft is not None:
                meta_payload["artifactDraft"] = artifact_draft
            yield ProviderEvent(kind="meta", metadata=meta_payload)
            if trace is not None:
                trace(
                    "tool_result_normalized",
                    {
                        "toolId": tool_result.tool_id,
                        "callId": tool_result.call_id,
                        "channel": tool_result.channel,
                        "success": tool_result.ok,
                        "artifactId": tool_result.artifact_id,
                        "native": True,
                    },
                )
                trace("turn_transition", turn_state.to_public_dict())
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call_id,
                    "content": _native_tool_message_content(tool_result),
                }
            )
            turn_state.drain_pending_input()
        if trace is not None:
            trace(
                "tool_loop_continued",
                {
                    "step": step_index + 1,
                    "native": True,
                    "lastToolId": native_tool_calls[-1]["function"]["name"],
                },
            )
        if step_index >= MAX_TOOL_STEPS - 1:
            turn_state.terminal_reason = "max_turns"
            if trace is not None:
                trace(
                    "tool_loop_max_steps",
                    {
                        "path": "native_tool_call",
                        "step": step_index + 1,
                        "contentLength": len(latest_content),
                    },
                )
                trace("turn_completed", turn_state.to_public_dict())
            cap_hint = _max_step_explanation()
            yield ProviderEvent(
                kind="delta",
                text=(latest_content + "\n\n" + cap_hint) if latest_content else cap_hint,
                provider_session_id=provider_session_id,
            )
            yield ProviderEvent(kind="final", provider_session_id=provider_session_id)
            return

    yield ProviderEvent(kind="final", provider_session_id=provider_session_id)


async def run_with_responses_tools(
    *,
    provider: ResponsesProvider,
    messages: list[dict[str, Any]],
    abort_event: asyncio.Event,
    model: str | None,
    instructions: str | None,
    plan: HarnessTurnPlan,
    tool_executor: ToolExecutor,
    tool_context: ToolExecutionContext,
    session_id: str | None,
    reasoning: dict[str, Any] | None = None,
    trace: TraceRecorder | None = None,
) -> AsyncIterator[ProviderEvent]:
    """Native Responses-API tool loop (Phase 2, HARNESS_REBUILD_V2).

    Owns the input[] array. Streams a response; collects function_call items via
    the provider's responsesFunctionCall meta events; executes each tool; appends
    function_call + function_call_output items to the array; re-POSTs. Emits the
    same toolCall / toolExecution meta + delta events as the other loops so the
    runtime's transcript-part assembly is unchanged. Reasoning summary deltas pass
    through as reasoning_delta events for the Phase 4 inline-thinking UX.
    """
    turn_state = TurnState(turn_id=plan.turn_id, decision_id=plan.decision_id)
    tool_schemas = build_responses_tool_schemas(plan.tools)
    working_messages: list[dict[str, Any]] = [dict(item) for item in messages]
    if trace is not None:
        trace("turn_started", turn_state.to_public_dict())

    for step_index in range(MAX_TOOL_STEPS):
        function_calls: list[dict[str, Any]] = []
        assistant_text_chunks: list[str] = []
        async for event in provider.stream_responses(
            messages=working_messages,
            tools=tool_schemas or None,
            model=model,
            instructions=instructions,
            prompt_cache_key=session_id,
            reasoning=reasoning,
            parallel_tool_calls=True,
            abort_event=abort_event,
        ):
            if event.kind == "delta":
                if event.text:
                    assistant_text_chunks.append(event.text)
                yield event
            elif event.kind == "reasoning_delta":
                yield event
            elif event.kind == "meta" and isinstance(event.metadata, dict):
                fc = event.metadata.get("responsesFunctionCall")
                if isinstance(fc, dict) and str(fc.get("name") or "").strip():
                    function_calls.append(fc)
        assistant_text = "".join(assistant_text_chunks).strip()
        if trace is not None:
            trace(
                "responses_turn_interpreted",
                {
                    "step": step_index + 1,
                    "functionCallCount": len(function_calls),
                    "contentLength": len(assistant_text),
                },
            )

        if not function_calls:
            turn_state.terminal_reason = "completed"
            if trace is not None:
                trace("turn_completed", turn_state.to_public_dict())
            yield ProviderEvent(kind="final")
            return

        # Append assistant text item (if any) so the model sees its own narration
        # on the next replay, then each function_call item.
        if assistant_text:
            working_messages.append(
                responses_items.assistant_message_item(
                    message_id=f"msg_{plan.turn_id}_{step_index}", text=assistant_text
                )
            )
        for call in function_calls:
            call_id = str(call.get("call_id") or "").strip() or _new_call_id(str(call.get("name") or "tool"))
            name = str(call.get("name") or "").strip()
            arguments_json = str(call.get("arguments") or "").strip() or "{}"
            arguments = _parse_native_tool_arguments(arguments_json)
            working_messages.append(
                responses_items.function_call_item(
                    item_id=str(call.get("id") or "") or f"fc_{call_id}",
                    call_id=call_id,
                    name=name,
                    arguments=arguments_json,
                )
            )
            request = ToolExecutionRequest(tool_id=name, arguments=arguments)
            if trace is not None:
                trace(
                    "tool_requested",
                    {
                        "toolId": name,
                        "arguments": arguments,
                        "step": step_index + 1,
                        "responses": True,
                        "callId": call_id,
                    },
                )
            yield ProviderEvent(
                kind="meta",
                metadata={
                    "toolCall": _tool_call_event_payload(
                        tool_id=name,
                        arguments=arguments,
                        step=step_index + 1,
                        turn_id=plan.turn_id,
                        decision_id=plan.decision_id,
                        native=True,
                        call_id=call_id,
                    ),
                    "turnState": turn_state.to_public_dict(),
                },
            )
            tool_result = await tool_executor(request, tool_context)
            tool_result = _force_call_id(tool_result, call_id)
            tool_result, artifact_draft = _materialize_tool_result_artifact(
                tool_result=tool_result,
                tool_context=tool_context,
                trace=trace,
            )
            turn_state.tool_call_count += 1
            turn_state.record_tool_step(
                tool_id=tool_result.tool_id,
                arguments=arguments,
                result=tool_result,
            )
            turn_state.queue_input(tool_result.to_runtime_input(), reason="tool_followup")
            meta_payload: dict[str, Any] = {
                "toolExecution": _tool_result_event_payload(
                    result=tool_result,
                    request=request,
                    plan=plan,
                ),
                "toolResult": tool_result.to_runtime_input(),
                "turnState": turn_state.to_public_dict(),
            }
            if artifact_draft is not None:
                meta_payload["artifactDraft"] = artifact_draft
            yield ProviderEvent(kind="meta", metadata=meta_payload)
            working_messages.append(
                responses_items.function_call_output_item(
                    call_id=call_id,
                    output=_native_tool_message_content(tool_result),
                )
            )
            turn_state.drain_pending_input()
            if trace is not None:
                trace("turn_transition", turn_state.to_public_dict())

        if step_index >= MAX_TOOL_STEPS - 1:
            turn_state.terminal_reason = "max_turns"
            if trace is not None:
                trace("turn_completed", turn_state.to_public_dict())
            yield ProviderEvent(kind="delta", text=_max_step_explanation())
            yield ProviderEvent(kind="final")
            return

    yield ProviderEvent(kind="final")


async def run_with_prompted_tools(
    *,
    provider: Provider,
    prompt: str,
    provider_session_id: str | None,
    abort_event: asyncio.Event,
    model: str | None,
    system_prompt: str | None,
    plan: HarnessTurnPlan,
    tool_executor: ToolExecutor,
    tool_context: ToolExecutionContext,
    trace: TraceRecorder | None,
) -> AsyncIterator[ProviderEvent]:
    """Run a bounded text-protocol tool loop for providers without native tools."""
    discovered_session = provider_session_id
    current_prompt = prompt
    current_system_prompt = compose_prompted_tool_system_prompt(
        provider=provider,
        system_prompt=system_prompt,
        tools=plan.tools,
    )
    turn_state = TurnState(turn_id=plan.turn_id, decision_id=plan.decision_id)
    if trace is not None:
        trace("turn_started", turn_state.to_public_dict())

    for step_index in range(MAX_TOOL_STEPS):
        events, discovered_session = await collect_provider_turn(
            provider=provider,
            prompt=current_prompt,
            provider_session_id=discovered_session,
            abort_event=abort_event,
            model=model,
            system_prompt=current_system_prompt,
            trace=trace,
            phase="prompted_tool",
        )
        assistant_text = "".join(event.text or "" for event in events if event.kind == "delta").strip()
        tool_requests = _extract_prompted_tool_requests(assistant_text)
        if trace is not None:
            trace(
                "prompted_tool_response_interpreted",
                {
                    "toolCallCount": len(tool_requests),
                    "contentLength": len(assistant_text),
                    "step": step_index + 1,
                },
            )
        if not tool_requests:
            turn_state.terminal_reason = "completed"
            if trace is not None:
                trace("turn_completed", turn_state.to_public_dict())
            if assistant_text:
                yield ProviderEvent(kind="delta", text=assistant_text, provider_session_id=discovered_session)
            yield ProviderEvent(kind="final", provider_session_id=discovered_session)
            return

        tool_payloads: list[str] = []
        for request in tool_requests:
            call_id = _new_call_id(request.tool_id)
            if trace is not None:
                trace(
                    "tool_requested",
                    {
                        "toolId": request.tool_id,
                        "arguments": request.arguments,
                        "step": step_index + 1,
                        "native": False,
                        "callId": call_id,
                    },
                )
            yield ProviderEvent(
                kind="meta",
                metadata={
                    "toolCall": _tool_call_event_payload(
                        tool_id=request.tool_id,
                        arguments=request.arguments,
                        step=step_index + 1,
                        turn_id=plan.turn_id,
                        decision_id=plan.decision_id,
                        native=False,
                        call_id=call_id,
                    ),
                    "turnState": turn_state.to_public_dict(),
                },
            )
            tool_result = await tool_executor(request, tool_context)
            tool_result = _force_call_id(tool_result, call_id)
            tool_result, artifact_draft = _materialize_tool_result_artifact(
                tool_result=tool_result,
                tool_context=tool_context,
                trace=trace,
            )
            turn_state.tool_call_count += 1
            turn_state.record_tool_step(
                tool_id=tool_result.tool_id,
                arguments=request.arguments,
                result=tool_result,
            )
            turn_state.queue_input(tool_result.to_runtime_input(), reason="tool_followup")
            meta_payload: dict[str, Any] = {
                "toolExecution": _tool_result_event_payload(
                    result=tool_result,
                    request=request,
                    plan=plan,
                ),
                "toolResult": tool_result.to_runtime_input(),
                "turnState": turn_state.to_public_dict(),
            }
            if artifact_draft is not None:
                meta_payload["artifactDraft"] = artifact_draft
            yield ProviderEvent(kind="meta", metadata=meta_payload)
            tool_payloads.append(tool_result.to_prompt_payload())
            turn_state.drain_pending_input()
            if trace is not None:
                trace("turn_transition", turn_state.to_public_dict())
        if step_index >= MAX_TOOL_STEPS - 1:
            turn_state.terminal_reason = "max_turns"
            if trace is not None:
                trace("turn_completed", turn_state.to_public_dict())
            yield ProviderEvent(
                kind="delta",
                text=_max_step_explanation(),
                provider_session_id=discovered_session,
            )
            yield ProviderEvent(kind="final", provider_session_id=discovered_session)
            return
        current_prompt = _compose_prompted_tool_followup(
            user_prompt=prompt,
            assistant_text=assistant_text,
            tool_payloads=tool_payloads,
        )

    turn_state.terminal_reason = "max_turns"
    if trace is not None:
        trace("turn_completed", turn_state.to_public_dict())
    yield ProviderEvent(kind="final", provider_session_id=discovered_session)


def _tool_call_event_payload(
    *,
    tool_id: str,
    arguments: dict[str, Any],
    step: int,
    turn_id: str | None = None,
    decision_id: str | None = None,
    channel: str = "tool",
    native: bool = False,
    call_id: str | None = None,
) -> dict[str, Any]:
    hint = None
    for key in ("path", "query", "pattern", "file", "dir", "uri"):
        value = arguments.get(key)
        if isinstance(value, str) and value.strip():
            hint = value.strip()
            break
    payload = {
        "toolId": tool_id,
        "arguments": dict(arguments),
        "target": hint,
        "hint": hint,
        "step": step,
        "channel": channel,
        "native": native,
    }
    # callId is stamped at request time (pre-execution) so the tool_call
    # transcript part shares an id with its paired tool_result. This is what
    # lets responses_items pair function_call <-> function_call_output on replay.
    if call_id:
        payload["callId"] = call_id
    if turn_id:
        payload["turnId"] = turn_id
    if decision_id:
        payload["decisionId"] = decision_id
    return payload


def _tool_result_event_payload(
    *,
    result: ToolExecutionResult,
    request: ToolExecutionRequest,
    plan: HarnessTurnPlan,
) -> dict[str, Any]:
    descriptor = next((tool for tool in plan.tools if tool.id == result.tool_id), None)
    return result.to_event_payload(
        turn_id=plan.turn_id,
        decision_id=plan.decision_id,
        arguments=request.arguments,
        evidence_role=descriptor.evidence_role if descriptor is not None else "none",
    )


def _extract_native_choice(response: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        raise RuntimeError("Native tool provider returned no choices.")
    choice = choices[0]
    if not isinstance(choice, dict):
        raise RuntimeError("Native tool provider returned an invalid choice payload.")
    message = choice.get("message")
    if not isinstance(message, dict):
        raise RuntimeError("Native tool provider returned no assistant message.")
    finish_reason = choice.get("finish_reason")
    return message, str(finish_reason).strip() if finish_reason is not None else None


def _coerce_native_message_content(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str) and text.strip():
                    parts.append(text.strip())
        return "\n".join(parts).strip()
    return ""


def _extract_native_tool_calls(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    rows: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        function = item.get("function")
        if not isinstance(function, dict):
            continue
        call_id = str(item.get("id") or "").strip() or f"call-{uuid4().hex[:10]}"
        name = str(function.get("name") or "").strip()
        if not name:
            continue
        rows.append(
            {
                "id": call_id,
                "type": "function",
                "function": {
                    "name": name,
                    "arguments": function.get("arguments"),
                },
            }
        )
    return rows


def _parse_native_tool_arguments(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return dict(parsed) if isinstance(parsed, dict) else {}


def _native_tool_message_content(tool_result: ToolExecutionResult) -> str:
    body = tool_result.body if tool_result.body is not None else tool_result.output
    if isinstance(body, str):
        return body
    return json.dumps(body, ensure_ascii=False, indent=2)


def compose_prompted_tool_system_prompt(
    *,
    provider: Provider,
    system_prompt: str | None,
    tools: list[ToolDescriptor],
) -> str | None:
    tool_lines = []
    for tool in tools:
        schema = json.dumps(tool.input_schema, ensure_ascii=False, sort_keys=True)
        tool_lines.append(f"- {tool.id}: {tool.description} Schema: {schema}")
    extra = (
        "You may request CopeNet tools by outputting only JSON objects, one object per tool call, when a tool is needed.\n"
        "Use this shape: {\"tool_id\":\"shell.exec\",\"arguments\":{\"command\":\"pwd\"}}.\n"
        "For shell commands, use one command per call. Do not use pipes, chaining, redirection, or multiple commands.\n"
        "If you output {\"command\":\"pwd\"}, CopeNet will treat it as shell.exec.\n"
        "After tool results are returned, answer using the observed output.\n\n"
        "Available tools:\n"
        + "\n".join(tool_lines)
    )
    return compose_system_prompt(provider=provider, system_prompt=system_prompt, extra_instructions=extra)


def _extract_prompted_tool_requests(text: str) -> list[ToolExecutionRequest]:
    decoder = json.JSONDecoder()
    requests: list[ToolExecutionRequest] = []
    index = 0
    while index < len(text):
        start = text.find("{", index)
        if start == -1:
            break
        try:
            value, end = decoder.raw_decode(text[start:])
        except json.JSONDecodeError:
            index = start + 1
            continue
        index = start + max(end, 1)
        request = _coerce_prompted_tool_request(value)
        if request is not None:
            requests.append(request)
    return requests


def _coerce_prompted_tool_request(value: Any) -> ToolExecutionRequest | None:
    if not isinstance(value, dict):
        return None
    raw_tool_id = value.get("tool_id") or value.get("toolId") or value.get("name")
    arguments = value.get("arguments")
    if raw_tool_id is None and isinstance(value.get("command"), str):
        return ToolExecutionRequest(tool_id="shell.exec", arguments={"command": str(value["command"])})
    tool_id = str(raw_tool_id or "").strip()
    if not tool_id:
        return None
    if not isinstance(arguments, dict):
        arguments = {key: item for key, item in value.items() if key not in {"tool_id", "toolId", "name"}}
    return ToolExecutionRequest(tool_id=tool_id, arguments=dict(arguments))


def _compose_prompted_tool_followup(*, user_prompt: str, assistant_text: str, tool_payloads: list[str]) -> str:
    return (
        "Continue the same task using the CopeNet tool results below. "
        "Do not repeat tool calls whose results are already provided unless another command is necessary.\n\n"
        f"Original user request:\n{user_prompt}\n\n"
        f"Assistant tool request text:\n{assistant_text}\n\n"
        "Tool results:\n"
        + "\n\n".join(tool_payloads)
        + "\n\nAnswer the user in plain text when you have enough information, "
        "or request another tool with JSON if you need more."
    )


def _force_call_id(result: ToolExecutionResult, call_id: str) -> ToolExecutionResult:
    """Stamp a pre-generated call_id so the tool_call/tool_result parts pair up."""
    if result.call_id == call_id:
        return result
    return ToolExecutionResult(
        tool_id=result.tool_id,
        call_id=call_id,
        channel=result.channel,
        ok=result.ok,
        summary=result.summary,
        body=result.body,
        output=dict(result.output),
        error=result.error,
        artifact_id=result.artifact_id,
    )


def _new_call_id(tool_id: str) -> str:
    return f"{tool_id}-{uuid4().hex[:10]}"


def _materialize_tool_result_artifact(
    *,
    tool_result: ToolExecutionResult,
    tool_context: ToolExecutionContext,
    trace: TraceRecorder | None,
) -> tuple[ToolExecutionResult, dict[str, Any] | None]:
    body = tool_result.body if tool_result.body is not None else tool_result.output
    payload_text = json.dumps(body, ensure_ascii=False, indent=2) if not isinstance(body, str) else body
    if not payload_text.strip():
        normalized = ToolExecutionResult(
            tool_id=tool_result.tool_id,
            call_id=tool_result.call_id,
            channel=tool_result.channel,
            ok=tool_result.ok,
            summary=tool_result.summary,
            body=f"({tool_result.tool_id} completed with no output)",
            output=dict(tool_result.output),
            error=tool_result.error,
            artifact_id=tool_result.artifact_id,
        )
        return normalized, None
    if len(payload_text) <= LARGE_TOOL_RESULT_CHAR_LIMIT or tool_context.artifact_store is None or not tool_context.session_key:
        if trace is not None and tool_result.call_id:
            trace(
                "tool_result_normalized",
                {
                    "toolId": tool_result.tool_id,
                    "callId": tool_result.call_id,
                    "channel": tool_result.channel,
                    "success": tool_result.ok,
                },
            )
        return tool_result, None

    artifact = tool_context.artifact_store.create(
        session_key=tool_context.session_key,
        run_id=tool_result.call_id or f"tool-{uuid4().hex[:8]}",
        artifact_type="tool_output",
        title=f"{tool_result.tool_id} output",
        body=payload_text,
        metadata={
            "toolId": tool_result.tool_id,
            "callId": tool_result.call_id,
            "channel": tool_result.channel,
            "persistedOutput": True,
        },
    )
    preview = payload_text[:280].strip()
    if len(payload_text) > 280:
        preview += "..."
    persisted_body = {
        "artifactId": artifact.artifact_id,
        "preview": preview,
        "persistedOutput": True,
    }
    persisted = ToolExecutionResult(
        tool_id=tool_result.tool_id,
        call_id=tool_result.call_id,
        channel=tool_result.channel,
        ok=tool_result.ok,
        summary=tool_result.summary,
        body=persisted_body,
        output=dict(tool_result.output),
        error=tool_result.error,
        artifact_id=artifact.artifact_id,
    )
    if trace is not None:
        trace(
            "tool_result_persisted",
            {
                "toolId": tool_result.tool_id,
                "callId": tool_result.call_id,
                "artifactId": artifact.artifact_id,
            },
        )
    return persisted, None


def compose_system_prompt(
    *,
    provider: Provider,
    system_prompt: str | None,
    extra_instructions: str | None = None,
) -> str | None:
    del provider
    parts = [part.strip() for part in (system_prompt or "", extra_instructions or "") if part and part.strip()]
    if not parts:
        return None
    return "\n\n".join(parts)


def compose_native_tool_system_prompt(
    *,
    provider: Provider,
    system_prompt: str | None,
) -> str | None:
    return compose_system_prompt(
        provider=provider,
        system_prompt=system_prompt,
        extra_instructions=(
            "Use provider-native tools when they help. "
            "Answer in plain text when ready."
        ),
    )


def provider_system_prompt(provider: Provider, system_prompt: str | None) -> str | None:
    if getattr(provider, "name", "") in {"claude-cli", "codex-cli"}:
        return None
    return system_prompt


def compose_provider_prompt(provider: Provider, prompt: str, system_prompt: str | None) -> str:
    if getattr(provider, "name", "") not in {"claude-cli", "codex-cli"} or not system_prompt:
        return prompt
    return (
        "System instructions:\n"
        f"{system_prompt}\n\n"
        "User request:\n"
        f"{prompt}"
    )
