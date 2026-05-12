"""Provider execution helpers and native tool calling for the CopeNet harness."""

from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator, Awaitable, Callable, Protocol
from uuid import uuid4

from copenet.core.runtime import TurnState
from copenet.core.tools import (
    ToolExecutionContext,
    ToolExecutionRequest,
    ToolExecutionResult,
    build_openai_tool_schemas,
)
from copenet.providers import Provider, ProviderEvent

from .planning import HarnessTurnPlan


ToolExecutor = Callable[[ToolExecutionRequest, ToolExecutionContext], Awaitable[ToolExecutionResult]]
TraceRecorder = Callable[[str, dict[str, Any] | None], None]
MAX_TOOL_STEPS = 4
LARGE_TOOL_RESULT_CHAR_LIMIT = 4000


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
    turn_state = TurnState()
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
            if trace is not None:
                trace(
                    "tool_requested",
                    {
                        "toolId": request.tool_id,
                        "arguments": request.arguments,
                        "step": step_index + 1,
                        "native": True,
                    },
                )
            yield ProviderEvent(
                kind="meta",
                metadata={
                    "toolCall": _tool_call_event_payload(
                        tool_id=request.tool_id,
                        arguments=request.arguments,
                        step=step_index + 1,
                        native=True,
                    ),
                    "turnState": turn_state.to_public_dict(),
                },
            )
            tool_result = await tool_executor(request, tool_context)
            tool_result = _with_call_id(tool_result, request.tool_id)
            tool_result = ToolExecutionResult(
                tool_id=tool_result.tool_id,
                call_id=native_call.get("id") or tool_result.call_id,
                channel=tool_result.channel,
                ok=tool_result.ok,
                summary=tool_result.summary,
                body=tool_result.body,
                output=dict(tool_result.output),
                error=tool_result.error,
                artifact_id=tool_result.artifact_id,
            )
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
                "toolExecution": tool_result.to_event_payload(),
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
                    "tool_call_id": native_call["id"],
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
            if latest_content:
                yield ProviderEvent(kind="delta", text=latest_content, provider_session_id=provider_session_id)
            yield ProviderEvent(kind="final", provider_session_id=provider_session_id)
            return

    yield ProviderEvent(kind="final", provider_session_id=provider_session_id)


def _tool_call_event_payload(
    *,
    tool_id: str,
    arguments: dict[str, Any],
    step: int,
    channel: str = "tool",
    native: bool = False,
) -> dict[str, Any]:
    hint = None
    for key in ("path", "query", "pattern", "file", "dir", "uri"):
        value = arguments.get(key)
        if isinstance(value, str) and value.strip():
            hint = value.strip()
            break
    return {
        "toolId": tool_id,
        "arguments": dict(arguments),
        "target": hint,
        "hint": hint,
        "step": step,
        "channel": channel,
        "native": native,
    }


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


def _with_call_id(result: ToolExecutionResult, tool_id: str) -> ToolExecutionResult:
    if result.call_id:
        return result
    return ToolExecutionResult(
        tool_id=result.tool_id,
        call_id=f"{tool_id}-{uuid4().hex[:10]}",
        channel=result.channel,
        ok=result.ok,
        summary=result.summary,
        body=result.body,
        output=dict(result.output),
        error=result.error,
        artifact_id=result.artifact_id,
    )


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
        extra_instructions="Use provider-native tools when they help. Answer in plain text when ready.",
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
