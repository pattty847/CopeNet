from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from copenet.core.harness import ChatHarness
from copenet.core.tools import (
    ToolDescriptor,
    ToolExecutionContext,
    ToolExecutionRequest,
    ToolExecutionResult,
    ToolPolicy,
)
from copenet.providers.claude_cli import ClaudeCliProvider
from copenet.runner.cli_runner import RunnerEvent, RunnerResult


class SequencedRecordingRunner:
    def __init__(self, turns: list[list[RunnerEvent | RunnerResult]]) -> None:
        self.turns = turns
        self.calls: list[dict[str, Any]] = []

    async def run(self, args, **kwargs):
        self.calls.append({"args": list(args), **kwargs})
        turn = self.turns[len(self.calls) - 1]
        for event in turn:
            yield event


def _tool_context(tmp_path: Path) -> ToolExecutionContext:
    return ToolExecutionContext(
        workdir=tmp_path,
        session_workspace_root=tmp_path,
        session_key="claude-contract",
        provider_name="claude-cli",
        model="claude-sonnet-4-6",
        session_store=None,  # type: ignore[arg-type]
        transcript_store=None,  # type: ignore[arg-type]
        providers={},
        policy=ToolPolicy(),
        available_tools=[],
        memory_service=None,
        workspace_intel_service=None,
        artifact_store=None,
        task_prompt_id=None,
        run_id="run-contract",
        trace=None,
    )


@pytest.mark.asyncio
async def test_claude_cli_prompt_and_tool_followup_contract(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Characterize all text and CLI arguments sent to Claude across a tool turn."""
    monkeypatch.setattr("shutil.which", lambda name: "/opt/homebrew/bin/claude" if name == "claude" else None)
    monkeypatch.setattr(
        "copenet.core.harness.tool_loop_prompted._new_call_id",
        lambda _tool_id: "call-fixed",
    )
    tool_request = json.dumps({"tool_id": "files.read", "arguments": {"path": "fixture.txt"}})
    runner = SequencedRecordingRunner(
        turns=[
            [
                RunnerEvent(
                    stream="stdout",
                    line=json.dumps(
                        {
                            "type": "assistant",
                            "session_id": "claude-session",
                            "message": {"content": [{"type": "text", "text": tool_request}]},
                        }
                    ),
                ),
                RunnerResult(returncode=0, stdout_tail="", stderr_tail=""),
            ],
            [
                RunnerEvent(
                    stream="stdout",
                    line=json.dumps(
                        {
                            "type": "assistant",
                            "session_id": "claude-session",
                            "message": {"content": [{"type": "text", "text": "The fixture says hello."}]},
                        }
                    ),
                ),
                RunnerResult(returncode=0, stdout_tail="", stderr_tail=""),
            ],
        ]
    )
    provider = ClaudeCliProvider(runner=runner)
    tool = ToolDescriptor(
        id="files.read",
        name="Read File",
        description="Read one fixture.",
        category="repo-read",
        input_schema={
            "type": "object",
            "properties": {"path": {"type": "string"}},
        },
        evidence_role="grounding",
        side_effect="read",
    )

    async def tool_executor(
        request: ToolExecutionRequest,
        _context: ToolExecutionContext,
    ) -> ToolExecutionResult:
        assert request == ToolExecutionRequest(
            tool_id="files.read",
            arguments={"path": "fixture.txt"},
        )
        return ToolExecutionResult(
            tool_id="files.read",
            ok=True,
            summary="Read fixture.txt",
            body="HELLO_SENTINEL",
        )

    _, stream = await ChatHarness().run_turn(
        provider=provider,
        prompt="Read fixture",
        provider_session_id=None,
        abort_event=asyncio.Event(),
        model="claude-sonnet-4-6",
        system_prompt="PROFILE_SENTINEL\n\nACCESS_SENTINEL",
        prompt_context_builder=lambda _plan: "PERSONA_SENTINEL\n\nMEMORY_SENTINEL",
        available_tools=[tool],
        tool_executor=tool_executor,
        tool_context=_tool_context(tmp_path),
    )
    events = [event async for event in stream]

    prompted_protocol = (
        "PROFILE_SENTINEL\n\nACCESS_SENTINEL\n\n"
        "PERSONA_SENTINEL\n\nMEMORY_SENTINEL\n\n"
        "You may request CopeNet tools by outputting only JSON objects, "
        "one object per tool call, when a tool is needed.\n"
        'Use this shape: {"tool_id":"shell.exec","arguments":{"command":"pwd"}}.\n'
        "For shell commands, use one command per call. Do not use pipes, chaining, redirection, or multiple commands.\n"
        'If you output {"command":"pwd"}, CopeNet will treat it as shell.exec.\n'
        "After tool results are returned, answer using the observed output.\n\n"
        "Available tools:\n"
        '- files.read: Read one fixture. Schema: {"properties": {"path": {"type": "string"}}, "type": "object"}'
    )
    first_prompt = (
        f"System instructions:\n{prompted_protocol}\n\n"
        "User request:\nRead fixture"
    )
    tool_result = json.dumps(
        {
            "callId": "call-fixed",
            "toolId": "files.read",
            "channel": "tool",
            "ok": True,
            "summary": "Read fixture.txt",
            "body": "HELLO_SENTINEL",
        },
        ensure_ascii=False,
        indent=2,
    )
    followup = (
        "Continue the same task using the CopeNet tool results below. "
        "Do not repeat tool calls whose results are already provided unless another command is necessary.\n\n"
        "Original user request:\nRead fixture\n\n"
        f"Assistant tool request text:\n{tool_request}\n\n"
        f"Tool results:\n{tool_result}\n\n"
        "Answer the user in plain text when you have enough information, "
        "or request another tool with JSON if you need more."
    )
    second_prompt = (
        f"System instructions:\n{prompted_protocol}\n\n"
        f"User request:\n{followup}"
    )

    assert [call["args"][2] for call in runner.calls] == [first_prompt, second_prompt]
    assert "--resume" not in runner.calls[0]["args"]
    assert runner.calls[1]["args"][-2:] == ["--resume", "claude-session"]
    for call in runner.calls:
        args = call["args"]
        assert args[:2] == ["/opt/homebrew/bin/claude", "-p"]
        assert args[args.index("--output-format") + 1] == "stream-json"
        assert args[args.index("--tools") + 1] == ""
        assert args[args.index("--model") + 1] == "claude-sonnet-4-6"
    assert [event.text for event in events if event.kind == "delta"] == ["The fixture says hello."]
