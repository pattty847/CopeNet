from __future__ import annotations

import asyncio
from typing import Any

import pytest

from copenet.providers.base import ProviderEvent
from copenet.providers.claude_cli import ClaudeCliProvider
from copenet.runner.cli_runner import RunnerEvent, RunnerResult


class RecordingRunner:
    def __init__(self, events: list[RunnerEvent | RunnerResult] | None = None) -> None:
        self.events = events or []
        self.calls: list[dict[str, Any]] = []

    async def run(self, args, **kwargs):
        self.calls.append({"args": list(args), **kwargs})
        for event in self.events:
            yield event


@pytest.fixture
def provider(monkeypatch: pytest.MonkeyPatch) -> ClaudeCliProvider:
    monkeypatch.setattr("shutil.which", lambda name: "/opt/homebrew/bin/claude" if name == "claude" else None)
    return ClaudeCliProvider(runner=RecordingRunner())


@pytest.mark.asyncio
async def test_claude_cli_list_models_exposes_openclaw_model_set(provider: ClaudeCliProvider) -> None:
    models = await provider.list_models()

    assert [model.id for model in models] == [
        "claude-opus-4-7",
        "claude-sonnet-4-6",
        "claude-opus-4-6",
        "claude-opus-4-5",
        "claude-sonnet-4-5",
        "claude-haiku-4-5",
    ]
    assert models[0].provider == "claude-cli"
    assert models[0].capabilities["toolCalls"] is False
    assert models[0].capabilities["promptedToolUse"] is True


@pytest.mark.asyncio
async def test_claude_cli_describe_reports_native_cli_auth(provider: ClaudeCliProvider) -> None:
    description = await provider.describe()

    assert description["id"] == "claude-cli"
    assert description["requiresAuth"] is True
    assert description["authType"] == "native-cli"
    assert description["capabilities"]["resume"] is True


def test_claude_cli_build_args_defaults_to_opus(provider: ClaudeCliProvider) -> None:
    args = provider._build_args(prompt="hello", provider_session_id=None, model=None)

    assert args == [
        "/opt/homebrew/bin/claude",
        "-p",
        "hello",
        "--output-format",
        "stream-json",
        "--verbose",
        "--tools",
        "",
        "--model",
        "claude-opus-4-7",
    ]


def test_claude_cli_build_args_resumes_existing_session(provider: ClaudeCliProvider) -> None:
    args = provider._build_args(prompt="hello", provider_session_id="session-123", model="claude-sonnet-4-6")

    assert "--resume" in args
    assert args[args.index("--resume") + 1] == "session-123"
    assert args[args.index("--model") + 1] == "claude-sonnet-4-6"


def test_claude_cli_build_args_rejects_unsupported_model(provider: ClaudeCliProvider) -> None:
    with pytest.raises(ValueError, match="unsupported claude cli model"):
        provider._build_args(prompt="hello", provider_session_id=None, model="claude-3-7-sonnet")


def test_claude_cli_parse_json_line_extracts_assistant_text_and_session() -> None:
    line = (
        '{"type":"assistant","session_id":"abc",'
        '"message":{"content":[{"type":"text","text":"hello"}]}}'
    )

    assert ClaudeCliProvider._parse_json_line(line) == ("hello", "abc")


def test_claude_cli_parse_json_line_extracts_result_text_and_session() -> None:
    line = '{"type":"result","session_id":"abc","result":"done"}'

    assert ClaudeCliProvider._parse_json_line(line) == ("done", "abc")


@pytest.mark.asyncio
async def test_claude_cli_run_streams_jsonl_and_persists_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("shutil.which", lambda name: "/opt/homebrew/bin/claude" if name == "claude" else None)
    runner = RecordingRunner(
        [
            RunnerEvent(
                stream="stdout",
                line='{"type":"assistant","session_id":"abc","message":{"content":[{"type":"text","text":"hi"}]}}',
            ),
            RunnerResult(returncode=0, stdout_tail="", stderr_tail=""),
        ]
    )
    subject = ClaudeCliProvider(runner=runner)

    events = [
        event
        async for event in subject.run(
            prompt="hello",
            provider_session_id=None,
            abort_event=asyncio.Event(),
            model="claude-sonnet-4-6",
        )
    ]

    assert events == [
        ProviderEvent(kind="meta", provider_session_id="abc"),
        ProviderEvent(kind="delta", text="hi"),
        ProviderEvent(kind="final", provider_session_id="abc"),
    ]
    assert runner.calls[0]["args"][runner.calls[0]["args"].index("--model") + 1] == "claude-sonnet-4-6"


@pytest.mark.asyncio
async def test_claude_cli_run_does_not_render_system_prompt_itself(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The harness embeds Claude's system text into prompt before this boundary."""
    monkeypatch.setattr("shutil.which", lambda name: "/opt/homebrew/bin/claude" if name == "claude" else None)
    runner = RecordingRunner([RunnerResult(returncode=0, stdout_tail="", stderr_tail="")])
    subject = ClaudeCliProvider(runner=runner)

    _ = [
        event
        async for event in subject.run(
            prompt="USER_PROMPT_SENTINEL",
            provider_session_id=None,
            abort_event=asyncio.Event(),
            model=None,
            system_prompt="SYSTEM_PROMPT_SENTINEL",
        )
    ]

    args = runner.calls[0]["args"]
    assert args[args.index("-p") + 1] == "USER_PROMPT_SENTINEL"
    assert "SYSTEM_PROMPT_SENTINEL" not in args


@pytest.mark.asyncio
async def test_claude_cli_run_does_not_duplicate_result_text(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("shutil.which", lambda name: "/opt/homebrew/bin/claude" if name == "claude" else None)
    runner = RecordingRunner(
        [
            RunnerEvent(
                stream="stdout",
                line='{"type":"assistant","session_id":"abc","message":{"content":[{"type":"text","text":"hi"}]}}',
            ),
            RunnerEvent(stream="stdout", line='{"type":"result","session_id":"abc","result":"hi"}'),
            RunnerResult(returncode=0, stdout_tail="", stderr_tail=""),
        ]
    )
    subject = ClaudeCliProvider(runner=runner)

    events = [
        event
        async for event in subject.run(
            prompt="hello",
            provider_session_id=None,
            abort_event=asyncio.Event(),
            model=None,
        )
    ]

    assert [event.text for event in events if event.kind == "delta"] == ["hi"]
