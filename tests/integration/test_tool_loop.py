import asyncio
from pathlib import Path

import pytest

from copenet.core.harness import ChatHarness
from copenet.core.orchestrator import ChatSendRequest, Orchestrator
from copenet.core.sessions import SessionStore, TranscriptStore
from copenet.core.tools import ToolExecutionContext, ToolExecutionRequest, ToolExecutionResult, ToolPolicy, ToolRegistry
from copenet.providers import ProviderEvent


class PromptedToolProvider:
    name = "prompted"
    display_name = "Prompted"

    def __init__(self, *, tool_json: str, follow_up: str = "Used tool result.") -> None:
        self.tool_json = tool_json
        self.follow_up = follow_up
        self.prompts: list[str] = []

    async def run(
        self,
        prompt: str,
        provider_session_id: str | None,
        abort_event: asyncio.Event,
        model: str | None = None,
        system_prompt: str | None = None,
    ):
        self.prompts.append(prompt)
        if len(self.prompts) == 1:
            yield ProviderEvent(kind="delta", text=self.tool_json, provider_session_id=provider_session_id or "provider-session")
            yield ProviderEvent(kind="final")
            return
        yield ProviderEvent(kind="delta", text=self.follow_up, provider_session_id=provider_session_id or "provider-session")
        yield ProviderEvent(kind="final")

    async def describe(self) -> dict:
        return {
            "id": self.name,
            "displayName": self.display_name,
            "available": True,
            "capabilities": {
                "chat": True,
                "streaming": True,
                "toolCalls": False,
                "promptedToolUse": True,
            },
        }

    async def list_models(self) -> list:
        return []


class PromptedBatchProvider(PromptedToolProvider):
    pass


class SequencedPromptProvider:
    name = "prompted"
    display_name = "Prompted"

    def __init__(self, outputs: list[str]) -> None:
        self.outputs = outputs
        self.prompts: list[str] = []
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
        text = self.outputs[self._index]
        self._index += 1
        yield ProviderEvent(kind="delta", text=text, provider_session_id=provider_session_id or "provider-session")
        yield ProviderEvent(kind="final")

    async def describe(self) -> dict:
        return {
            "id": self.name,
            "displayName": self.display_name,
            "available": True,
            "capabilities": {
                "chat": True,
                "streaming": True,
                "toolCalls": False,
                "promptedToolUse": True,
            },
        }

    async def list_models(self) -> list:
        return []


async def _collect(orchestrator: Orchestrator, request: ChatSendRequest) -> tuple[dict, list[dict]]:
    events: list[dict] = []

    async def emit(payload: dict) -> None:
        events.append(payload)

    result = await orchestrator.send_chat(request, emit=emit)
    return result, events


@pytest.mark.asyncio
async def test_orchestrator_tool_loop_reads_file(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("COPNET_WORKDIR", str(tmp_path))
    (tmp_path / "README.md").write_text("# Temp Repo\nHello\n", encoding="utf-8")
    provider = PromptedToolProvider(
        tool_json='{"tool_id":"files.read","arguments":{"path":"README.md"}}',
        follow_up="Used the file result to answer.",
    )
    orchestrator = Orchestrator(
        session_store=SessionStore(path=tmp_path / "index.json"),
        transcript_store=TranscriptStore(root_dir=tmp_path),
        sessions_dir=tmp_path,
        providers={"prompted": provider},
    )

    result, events = await _collect(
        orchestrator,
        ChatSendRequest(session_key="alpha", message="Read the README", provider="prompted"),
    )

    assert result["status"] == "ok"
    final_event = events[-1]
    assert final_event["state"] == "final"
    assert final_event["toolExecution"]["toolId"] == "files.read"
    assert final_event["toolExecution"]["ok"] is True
    history = orchestrator.history("alpha")
    assert history[-1]["toolExecution"]["toolId"] == "files.read"


@pytest.mark.asyncio
async def test_orchestrator_tool_loop_blocks_path_escape(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("COPNET_WORKDIR", str(tmp_path))
    provider = PromptedToolProvider(
        tool_json='{"tool_id":"files.list","arguments":{"path":"/Users/copeharder/Desktop"}}',
        follow_up="The tool was blocked, so I cannot inspect that path.",
    )
    orchestrator = Orchestrator(
        session_store=SessionStore(path=tmp_path / "index.json"),
        transcript_store=TranscriptStore(root_dir=tmp_path),
        sessions_dir=tmp_path,
        providers={"prompted": provider},
    )

    _, events = await _collect(
        orchestrator,
        ChatSendRequest(session_key="alpha", message="Read the desktop", provider="prompted"),
    )

    final_event = events[-1]
    assert final_event["toolExecution"]["toolId"] == "files.list"
    assert final_event["toolExecution"]["ok"] is False
    assert "path escapes workdir" in final_event["toolExecution"]["error"]


@pytest.mark.asyncio
async def test_harness_continues_read_only_tool_loop_until_answer(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Temp Repo\nHello\n", encoding="utf-8")
    provider = SequencedPromptProvider(
        outputs=[
            '{"tool_id":"files.list","arguments":{"path":"."}}',
            '{"tool_id":"files.read","arguments":{"path":"README.md"}}',
            "The repository contains a README and I inspected it successfully.",
        ],
    )
    harness = ChatHarness()
    tool_calls: list[ToolExecutionRequest] = []

    async def tool_executor(request: ToolExecutionRequest, context: ToolExecutionContext) -> ToolExecutionResult:
        tool_calls.append(request)
        return ToolExecutionResult(
            tool_id=request.tool_id,
            ok=True,
            summary="ok",
            output={"entries": []},
        )

    tool_context = ToolExecutionContext(
        workdir=tmp_path,
        session_key=None,
        provider_name="prompted",
        model=None,
        session_store=SessionStore(path=tmp_path / "index.json"),
        transcript_store=TranscriptStore(root_dir=tmp_path / "history"),
        providers={"prompted": provider},
        policy=ToolPolicy(),
        trace=None,
    )
    plan, stream = await harness.run_turn(
        provider=provider,
        prompt="Inspect the repo",
        provider_session_id=None,
        abort_event=asyncio.Event(),
        available_tools=ToolRegistry().list_tools(),
        tool_executor=tool_executor,
        tool_context=tool_context,
    )
    events = [event async for event in stream]

    assert plan.will_attempt_tool_loop is True
    assert [call.tool_id for call in tool_calls] == ["files.list", "files.read"]
    meta_events = [event for event in events if event.kind == "meta"]
    assert len(meta_events) == 2
    delta_text = "".join(event.text or "" for event in events if event.kind == "delta")
    assert "inspected it successfully" in delta_text


@pytest.mark.asyncio
async def test_harness_executes_safe_read_batch_and_emits_meta(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Temp Repo\nHello\n", encoding="utf-8")
    provider = PromptedBatchProvider(
        tool_json=(
            '{"tool_calls":['
            '{"tool_id":"files.list","arguments":{"path":"."}},'
            '{"tool_id":"files.read","arguments":{"path":"README.md"}}'
            ']}'
        ),
        follow_up="Used the merged tool bundle to answer.",
    )
    traces: list[tuple[str, dict | None]] = []

    def trace(event: str, payload: dict | None = None) -> None:
        traces.append((event, payload))

    harness = ChatHarness()
    registry = ToolRegistry()
    tool_context = ToolExecutionContext(
        workdir=tmp_path,
        session_key="alpha",
        provider_name="prompted",
        model=None,
        session_store=SessionStore(path=tmp_path / "index.json"),
        transcript_store=TranscriptStore(root_dir=tmp_path / "history"),
        providers={"prompted": provider},
        policy=ToolPolicy(),
        trace=trace,
    )
    _, stream = await harness.run_turn(
        provider=provider,
        prompt="Inspect the repo",
        provider_session_id=None,
        abort_event=asyncio.Event(),
        available_tools=registry.list_tools(),
        tool_executor=registry.execute,
        tool_context=tool_context,
        trace=trace,
    )
    events = [event async for event in stream]

    meta_event = next(event for event in events if event.kind == "meta")
    assert meta_event.metadata["toolExecution"]["toolId"] == "tool.batch"
    assert meta_event.metadata["toolExecution"]["ok"] is True
    assert meta_event.metadata["artifactDraft"]["type"] == "tool_bundle"
    assert any(event == "batch_planned" for event, _ in traces)
    assert any(event == "batch_executed" for event, _ in traces)
    assert any(event == "batch_merged" for event, _ in traces)


@pytest.mark.asyncio
async def test_harness_blocks_unsafe_batch_request(tmp_path: Path) -> None:
    provider = PromptedBatchProvider(
        tool_json=(
            '{"tool_calls":['
            '{"tool_id":"files.list","arguments":{"path":"."}},'
            '{"tool_id":"git.status","arguments":{}}'
            ']}'
        ),
        follow_up="The batch request was blocked.",
    )
    traces: list[tuple[str, dict | None]] = []

    def trace(event: str, payload: dict | None = None) -> None:
        traces.append((event, payload))

    harness = ChatHarness()
    registry = ToolRegistry()
    tool_context = ToolExecutionContext(
        workdir=tmp_path,
        session_key="alpha",
        provider_name="prompted",
        model=None,
        session_store=SessionStore(path=tmp_path / "index.json"),
        transcript_store=TranscriptStore(root_dir=tmp_path / "history"),
        providers={"prompted": provider},
        policy=ToolPolicy(),
        trace=trace,
    )
    _, stream = await harness.run_turn(
        provider=provider,
        prompt="Inspect the repo",
        provider_session_id=None,
        abort_event=asyncio.Event(),
        available_tools=registry.list_tools(),
        tool_executor=registry.execute,
        tool_context=tool_context,
        trace=trace,
    )
    events = [event async for event in stream]

    meta_event = next(event for event in events if event.kind == "meta")
    assert meta_event.metadata["toolExecution"]["toolId"] == "tool.batch"
    assert meta_event.metadata["toolExecution"]["ok"] is False
    assert any(event == "tool_blocked" for event, _ in traces)
