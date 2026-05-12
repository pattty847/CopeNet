import asyncio
from pathlib import Path
from typing import Any

import pytest

from copenet.core.harness import ChatHarness
from copenet.core.sessions import SessionStore, TranscriptStore
from copenet.core.tools import ToolExecutionContext, ToolPolicy, ToolRegistry
from copenet.providers import ProviderEvent


TraceRow = tuple[str, dict[str, Any] | None]


class ScriptedPromptProvider:
    name = "scripted"
    display_name = "Scripted"

    def __init__(self, outputs: list[str]) -> None:
        self._outputs = outputs
        self.prompts: list[str] = []
        self.system_prompts: list[str | None] = []
        self._index = 0

    async def run(
        self,
        prompt: str,
        provider_session_id: str | None,
        abort_event: asyncio.Event,
        model: str | None = None,
        system_prompt: str | None = None,
    ):
        self.prompts.append(prompt)
        self.system_prompts.append(system_prompt)
        text = self._outputs[self._index]
        self._index += 1
        yield ProviderEvent(kind="delta", text=text, provider_session_id=provider_session_id or "provider-session")
        yield ProviderEvent(kind="final")

    async def describe(self) -> dict[str, Any]:
        return {
            "id": self.name,
            "displayName": self.display_name,
            "available": True,
            "capabilities": {
                "chat": True,
                "streaming": True,
                "toolCalls": False,
                "promptedToolUse": True,
                "resume": True,
            },
        }

    async def list_models(self) -> list:
        return []


async def _run_harness_turn(
    *,
    provider: ScriptedPromptProvider,
    prompt: str,
    tmp_path: Path,
    provider_session_id: str | None = None,
) -> tuple[list[ProviderEvent], list[TraceRow], str | None]:
    traces: list[TraceRow] = []

    def trace(event: str, payload: dict[str, Any] | None = None) -> None:
        traces.append((event, payload))

    harness = ChatHarness()
    registry = ToolRegistry()
    tool_context = ToolExecutionContext(
        workdir=tmp_path,
        session_workspace_root=tmp_path,
        session_key="alpha",
        provider_name=provider.name,
        model=None,
        session_store=SessionStore(path=tmp_path / "index.json"),
        transcript_store=TranscriptStore(root_dir=tmp_path / "history"),
        providers={provider.name: provider},
        policy=ToolPolicy(),
        trace=trace,
    )
    plan, stream = await harness.run_turn(
        provider=provider,
        prompt=prompt,
        provider_session_id=provider_session_id,
        abort_event=asyncio.Event(),
        available_tools=registry.list_tools(),
        tool_executor=registry.execute,
        tool_context=tool_context,
        trace=trace,
    )
    events = [event async for event in stream]
    discovered_session_id = next(
        (event.provider_session_id for event in events if event.provider_session_id),
        provider_session_id,
    )

    assert plan.will_attempt_tool_loop is False
    assert plan.tool_execution_mode == "none"
    assert any(event == "harness_planned" for event, _ in traces)
    return events, traces, discovered_session_id


def _find_trace_rows(traces: list[TraceRow], event: str) -> list[dict[str, Any]]:
    return [payload or {} for trace_event, payload in traces if trace_event == event]


@pytest.mark.asyncio
async def test_prompted_provider_streams_plain_text_without_harness_tool_parsing(tmp_path: Path) -> None:
    provider = ScriptedPromptProvider(outputs=['{"tool_id":"files.read","arguments":{"path":"README.md"}}'])

    events, traces, provider_session_id = await _run_harness_turn(
        provider=provider,
        prompt="Please use a tool if needed and then answer briefly.",
        tmp_path=tmp_path,
    )

    assert provider_session_id == "provider-session"
    assert len(provider.prompts) == 1
    assert provider.system_prompts == [None]
    assert _find_trace_rows(traces, "tool_requested") == []
    assert _find_trace_rows(traces, "tool_executed") == []
    delta_events = [event for event in events if event.kind == "delta"]
    assert delta_events[0].text == '{"tool_id":"files.read","arguments":{"path":"README.md"}}'


@pytest.mark.asyncio
async def test_prompted_provider_resume_remains_provider_passthrough(tmp_path: Path) -> None:
    provider = ScriptedPromptProvider(outputs=["First answer.", "Second answer."])

    first_events, _, provider_session_id = await _run_harness_turn(
        provider=provider,
        prompt="Please answer.",
        tmp_path=tmp_path,
    )
    second_events, _, resumed_session_id = await _run_harness_turn(
        provider=provider,
        prompt="Please answer again.",
        tmp_path=tmp_path,
        provider_session_id=provider_session_id,
    )

    assert provider_session_id == resumed_session_id == "provider-session"
    assert [event.text for event in first_events if event.kind == "delta"] == ["First answer."]
    assert [event.text for event in second_events if event.kind == "delta"] == ["Second answer."]
