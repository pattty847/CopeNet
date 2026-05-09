import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from copenet.core.harness import ChatHarness
from copenet.core.sessions import SessionStore, TranscriptStore
from copenet.core.tools import ToolExecutionContext, ToolPolicy, ToolRegistry
from copenet.providers import ProviderEvent


TraceRow = tuple[str, dict[str, Any] | None]


@dataclass(frozen=True)
class PromptMatrixCase:
    name: str
    first_turn: str
    follow_up: str | None
    expect_tool_requested: bool
    expect_correction: bool
    expected_tool_id: str | None
    expect_tool_ok: bool | None
    expect_trace_event: str | None


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
        yield ProviderEvent(
            kind="delta",
            text=text,
            provider_session_id=provider_session_id or "provider-session",
        )
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
    expect_tool_loop: bool = True,
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

    assert plan.will_attempt_tool_loop is expect_tool_loop
    assert any(event == "harness_planned" for event, _ in traces)
    return events, traces, discovered_session_id


def _find_trace_rows(traces: list[TraceRow], event: str) -> list[dict[str, Any]]:
    return [payload or {} for trace_event, payload in traces if trace_event == event]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    [
        PromptMatrixCase(
            name="exact_json_success",
            first_turn='{"tool_id":"files.list","arguments":{"path":"."}}',
            follow_up="Tool succeeded.",
            expect_tool_requested=True,
            expect_correction=False,
            expected_tool_id="files.list",
            expect_tool_ok=True,
            expect_trace_event="tool_executed",
        ),
        PromptMatrixCase(
            name="json_with_whitespace_success",
            first_turn='\n  {"tool_id":"files.read","arguments":{"path":"README.md"}}  \n',
            follow_up="Read the README successfully.",
            expect_tool_requested=True,
            expect_correction=False,
            expected_tool_id="files.read",
            expect_tool_ok=True,
            expect_trace_event="tool_executed",
        ),
        PromptMatrixCase(
            name="prose_refusal_no_tool_request",
            first_turn="I cannot use files.list here because that tool is not available in this environment.",
            follow_up=None,
            expect_tool_requested=False,
            expect_correction=False,
            expected_tool_id=None,
            expect_tool_ok=None,
            expect_trace_event=None,
        ),
        PromptMatrixCase(
            name="malformed_json_correction_retry",
            first_turn='{"tool_id":"files.list","arguments":{"path":"."}',
            follow_up="I repaired the tool request and can answer without another tool.",
            expect_tool_requested=False,
            expect_correction=True,
            expected_tool_id=None,
            expect_tool_ok=None,
            expect_trace_event=None,
        ),
        PromptMatrixCase(
            name="wrong_shape_json_correction_retry",
            first_turn='{"tool":"files.list","arguments":{"path":"."}}',
            follow_up="I repaired the tool request and can answer without another tool.",
            expect_tool_requested=False,
            expect_correction=True,
            expected_tool_id=None,
            expect_tool_ok=None,
            expect_trace_event=None,
        ),
        PromptMatrixCase(
            name="outside_workspace_path_request",
            first_turn='{"tool_id":"files.list","arguments":{"path":".."}}',
            follow_up="I inspected the parent directory and marked it as outside the home workspace.",
            expect_tool_requested=True,
            expect_correction=False,
            expected_tool_id="files.list",
            expect_tool_ok=True,
            expect_trace_event="tool_executed",
        ),
        PromptMatrixCase(
            name="wrong_but_valid_tool_json",
            first_turn='{"tool_id":"git.status","arguments":{}}',
            follow_up="Reported git status instead.",
            expect_tool_requested=True,
            expect_correction=False,
            expected_tool_id="git.status",
            expect_tool_ok=False,
            expect_trace_event="tool_executed",
        ),
    ],
    ids=lambda case: case.name,
)
async def test_tool_prompt_matrix_behaviors(case: PromptMatrixCase, tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Temp Repo\nHello\n", encoding="utf-8")
    outputs = [case.first_turn]
    if case.follow_up is not None:
        outputs.append(case.follow_up)
    provider = ScriptedPromptProvider(outputs=outputs)

    events, traces, _ = await _run_harness_turn(
        provider=provider,
        prompt="Please use a tool if needed and then answer briefly.",
        tmp_path=tmp_path,
    )

    tool_requested = _find_trace_rows(traces, "tool_requested")
    if case.expect_tool_requested:
        assert len(tool_requested) == 1
        assert tool_requested[0]["toolId"] == case.expected_tool_id
        tool_meta_events = [event for event in events if event.kind == "meta" and "toolExecution" in event.metadata]
        assert len(tool_meta_events) == 1
        tool_payload = tool_meta_events[0].metadata["toolExecution"]
        assert tool_payload["toolId"] == case.expected_tool_id
        assert tool_payload["ok"] is case.expect_tool_ok
        if case.name == "outside_workspace_path_request":
            assert tool_payload["scope"] == "outside_workspace"
        if case.expect_trace_event is not None:
            matching = _find_trace_rows(traces, case.expect_trace_event)
            assert len(matching) == 1
            assert matching[0]["toolId"] == case.expected_tool_id
        follow_up_events = [event for event in events if event.kind == "delta"]
        assert follow_up_events[-1].text == case.follow_up
    else:
        assert tool_requested == []
        assert _find_trace_rows(traces, "tool_executed") == []
        assert _find_trace_rows(traces, "tool_blocked") == []
        if case.expect_correction:
            correction_rows = _find_trace_rows(traces, "tool_correction_generated")
            assert len(correction_rows) == 1
            tool_meta_events = [event for event in events if event.kind == "meta" and "toolExecution" in event.metadata]
            assert len(tool_meta_events) == 1
            assert tool_meta_events[0].metadata["toolExecution"]["toolId"] == "tool.parse"
        else:
            assert all(event.kind != "meta" for event in events)
        delta_events = [event for event in events if event.kind == "delta"]
        assert len(delta_events) == 1
        assert delta_events[0].text == (case.follow_up or case.first_turn)


@pytest.mark.asyncio
async def test_tool_prompt_matrix_resume_drift_is_visible_in_traces(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Temp Repo\nHello\n", encoding="utf-8")
    provider = ScriptedPromptProvider(
        outputs=[
            '{"tool_id":"files.read","arguments":{"path":"README.md"}}',
            '{"state":"FINAL_CANDIDATE","answer":"Used the README contents to answer.","evidence":["README.md"],"done_conditions_met":["grounded evidence"],"remaining_uncertainty":[]}',
            "I cannot use files.read here because that tool is not actually available in this environment.",
            '{"tool_id":"files.read","arguments":{"path":"README.md"}}',
            '{"state":"FINAL_CANDIDATE","answer":"Used the README contents to answer after repairing the resumed tool request.","evidence":["README.md"],"done_conditions_met":["grounded evidence"],"remaining_uncertainty":["resume drift required one repair"]}',
        ]
    )

    first_events, first_traces, provider_session_id = await _run_harness_turn(
        provider=provider,
        prompt="Please use a tool to read the README.",
        tmp_path=tmp_path,
    )
    second_events, second_traces, resumed_session_id = await _run_harness_turn(
        provider=provider,
        prompt="Please use a tool to read the README again.",
        tmp_path=tmp_path,
        provider_session_id=provider_session_id,
    )

    first_tool_request = _find_trace_rows(first_traces, "tool_requested")
    second_tool_request = _find_trace_rows(second_traces, "tool_requested")

    assert provider_session_id == resumed_session_id == "provider-session"
    assert len(first_tool_request) == 1


@pytest.mark.asyncio
async def test_soft_harness_feedback_prompt_stays_conversational(tmp_path: Path) -> None:
    provider = ScriptedPromptProvider(outputs=["Just answer casually."])

    events, traces, _ = await _run_harness_turn(
        provider=provider,
        prompt="What do you think of this harness direction? I want the vibe to feel less constrained.",
        tmp_path=tmp_path,
        expect_tool_loop=False,
    )

    planned = _find_trace_rows(traces, "harness_planned")
    assert planned[0]["interactionClass"] == "advisory"
    assert planned[0]["willAttemptToolLoop"] is False
    assert planned[0]["toolLoopSuppressedReason"] == "interaction_class_advisory"
    assert "Respond with exactly one legal JSON action" not in provider.prompts[0]
    delta_events = [event for event in events if event.kind == "delta"]
    assert delta_events[0].text == "Just answer casually."


@pytest.mark.asyncio
async def test_explicit_repo_inspection_prompt_uses_tool_loop_prompt_shape(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Temp Repo\nHello\n", encoding="utf-8")
    provider = ScriptedPromptProvider(
        outputs=[
            '{"tool_id":"files.read","arguments":{"path":"README.md"}}',
            '{"state":"FINAL_CANDIDATE","answer":"Grounded answer.","evidence":["README.md"],"done_conditions_met":["grounded file evidence","file path citation"],"remaining_uncertainty":[]}',
        ]
    )

    events, traces, _ = await _run_harness_turn(
        provider=provider,
        prompt="Inspect the repo and explain the architecture with grounded evidence.",
        tmp_path=tmp_path,
    )

    planned = _find_trace_rows(traces, "harness_planned")
    assert planned[0]["interactionClass"] == "agent"
    assert planned[0]["willAttemptToolLoop"] is True
    assert "Respond with exactly one legal JSON action" in provider.prompts[0]
    tool_requests = _find_trace_rows(traces, "tool_requested")
    assert tool_requests[0]["toolId"] == "files.read"
    assert _find_trace_rows(traces, "tool_executed")[0]["toolId"] == "files.read"
    assert any(event.kind == "meta" for event in events)


@pytest.mark.asyncio
async def test_tool_system_prompt_declares_capability_manifest_for_read_only_mode(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Temp Repo\nHello\n", encoding="utf-8")
    provider = ScriptedPromptProvider(
        outputs=[
            '{"tool_id":"files.read","arguments":{"path":"README.md"}}',
            '{"state":"FINAL_CANDIDATE","answer":"Read complete.","evidence":["README.md"],"done_conditions_met":["grounded evidence"],"remaining_uncertainty":[]}',
        ]
    )
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
        policy=ToolPolicy(allowed_categories={"repo-read", "shell-read", "context", "artifact"}),
        trace=trace,
    )
    _, stream = await harness.run_turn(
        provider=provider,
        prompt="Read the README then answer.",
        provider_session_id=None,
        abort_event=asyncio.Event(),
        available_tools=registry.list_tools(),
        tool_executor=registry.execute,
        tool_context=tool_context,
        trace=trace,
    )
    _ = [event async for event in stream]

    system_prompt = provider.system_prompts[0] or ""
    assert "Workspace root:" in system_prompt
    assert "Tool mode:" in system_prompt
    assert "Available tool ids:" in system_prompt
    assert "Unavailable capability classes:" in system_prompt
    assert "repo-write" in system_prompt
    assert "TOOL_BATCH only supports read-only repo/context work" in system_prompt
