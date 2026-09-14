"""Responses-lane provider fake for orchestrator-level tests.

The Chat Completions loop used to be the suite's in-process tool-loop vehicle.
It was removed with the local runtimes (2026-09-13), so tests that drive a
tool-using turn through `Orchestrator.send_chat` now script this fake, which
speaks the same `stream_responses` contract as openai-codex.

Scripting styles:

- `calls=[(tool_id, arguments_or_callable), ...]` — one tool call per model
  call, then `final_text`. A callable receives the input array and returns the
  arguments (the chart tests compute anchors from the delivered packet).
- `outputs=[...]` — one string per model call: JSON `{"tool_id", "arguments"}`
  becomes a tool call, anything else is the final text.
- subclass and override `next_step(messages)` to return `("tool", id, args)`,
  `("text", text)` or `None` (meaning "finish with final_text").

`prompted=True` turns the fake into a text-protocol provider (the claude-cli
lane) that answers through `run()` instead.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator, Callable

from copenet.providers import ProviderEvent, ProviderModel, resolved_model_event

COMPLETED = ProviderEvent(kind="meta", metadata={"responsesCompleted": True})


def function_call_event(call_id: str, name: str, arguments: dict[str, Any] | str) -> ProviderEvent:
    return ProviderEvent(
        kind="meta",
        metadata={
            "responsesFunctionCall": {
                "id": f"fc_{call_id}",
                "call_id": call_id,
                "name": name,
                "arguments": arguments if isinstance(arguments, str) else json.dumps(arguments),
            }
        },
    )


def dotted_tool_id(safe_name: str) -> str:
    """Reverse the Responses-API name sanitization; CopeNet tool ids carry no underscores."""
    return safe_name.replace("_", ".")


def user_texts(messages: list[dict[str, Any]]) -> list[str]:
    texts: list[str] = []
    for item in messages:
        if item.get("role") != "user" or item.get("type") not in (None, "message"):
            continue
        content = item.get("content")
        if isinstance(content, str):
            texts.append(content)
        elif isinstance(content, list):
            texts.append("".join(str(part.get("text") or "") for part in content if isinstance(part, dict)))
    return texts


def user_text(messages: list[dict[str, Any]]) -> str:
    return "\n".join(user_texts(messages))


def tool_outputs(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [item for item in messages if item.get("type") == "function_call_output"]


class ScriptedResponsesProvider:
    name = "scripted-responses"
    display_name = "Scripted Responses"

    def __init__(
        self,
        *,
        name: str | None = None,
        display_name: str | None = None,
        calls: list[tuple[str, Any]] | tuple = (),
        outputs: list[str] | None = None,
        final_text: str = "Done.",
        prompted: bool = False,
        resolved_model: str | None = None,
        models: list[ProviderModel] | None = None,
    ) -> None:
        if name:
            self.name = name
        if display_name:
            self.display_name = display_name
        self.calls: list[tuple[str, Any]] = list(calls)
        self.outputs: list[str] | None = list(outputs) if outputs is not None else None
        self.final_text = final_text
        self.prompted = prompted
        self.resolved_model = resolved_model
        self._models = list(models or [])
        self.messages: list[list[dict[str, Any]]] = []
        self.tool_names: list[list[str]] = []
        self.instructions: list[str | None] = []
        self.prompts: list[str] = []
        self.system_prompts: list[str | None] = []
        self._call_count = 0

    # -- scripting -----------------------------------------------------------

    def next_step(self, messages: list[dict[str, Any]]) -> tuple | None:
        if self.calls:
            name, arguments = self.calls.pop(0)
            if callable(arguments):
                arguments = arguments(messages)
            return ("tool", name, arguments)
        if self.outputs:
            text = self.outputs.pop(0)
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, dict) and parsed.get("tool_id"):
                return ("tool", parsed["tool_id"], parsed.get("arguments") or {})
            return ("text", text)
        return None

    # -- provider contract ---------------------------------------------------

    async def describe(self) -> dict[str, Any]:
        capabilities = (
            {"chat": True, "streaming": True, "toolCalls": False, "promptedToolUse": True, "resume": True}
            if self.prompted
            else {"chat": True, "streaming": True, "toolCalls": False, "promptedToolUse": True, "responsesApi": True}
        )
        return {"id": self.name, "displayName": self.display_name, "available": True, "capabilities": capabilities}

    async def list_models(self) -> list[ProviderModel]:
        return list(self._models)

    async def run(
        self,
        prompt: str,
        provider_session_id: str | None,
        abort_event: asyncio.Event,
        model: str | None = None,
        system_prompt: str | None = None,
    ):
        if not self.prompted:
            raise AssertionError("a responses provider must be driven through stream_responses, not run()")
        self.prompts.append(prompt)
        self.system_prompts.append(system_prompt)
        step = self.next_step([{"role": "user", "content": prompt}])
        text = self.final_text if step is None else step[1] if step[0] == "text" else json.dumps({"tool_id": step[1], "arguments": step[2]})
        yield ProviderEvent(kind="delta", text=text, provider_session_id=provider_session_id or f"{self.name}-session")
        yield ProviderEvent(kind="final", provider_session_id=provider_session_id or f"{self.name}-session")

    async def stream_responses(
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
        del model, prompt_cache_key, reasoning, parallel_tool_calls, abort_event
        self.messages.append([dict(item) for item in messages])
        self.tool_names.append([dotted_tool_id(str(tool.get("name") or "")) for tool in tools or []])
        self.instructions.append(instructions)
        self._call_count += 1
        announcement = resolved_model_event(self.resolved_model)
        if announcement is not None:
            yield announcement
        step = await self._resolve_step(messages)
        if step is not None and step[0] == "tool":
            call_id = step[3] if len(step) > 3 else f"call-{self._call_count}"
            yield function_call_event(call_id, step[1], step[2])
        else:
            yield ProviderEvent(kind="delta", text=self.final_text if step is None else step[1])
        yield COMPLETED

    async def _resolve_step(self, messages: list[dict[str, Any]]) -> tuple | None:
        step = self.next_step(messages)
        if asyncio.iscoroutine(step):
            step = await step
        return step


ScriptStep = Callable[[list[dict[str, Any]]], tuple | None]
