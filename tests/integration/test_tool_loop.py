import asyncio
from pathlib import Path

import pytest

from copenet.core.harness import ChatHarness
from copenet.core.orchestrator import ChatSendRequest, Orchestrator
from copenet.core.runtime import ArtifactStore
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


class NativeToolProvider:
    name = "lm-studio"
    display_name = "LM Studio"

    def __init__(self, responses: list[dict]) -> None:
        self.responses = responses
        self.messages: list[list[dict]] = []
        self.tool_payloads: list[list[dict] | None] = []
        self._index = 0

    async def run(
        self,
        prompt: str,
        provider_session_id: str | None,
        abort_event: asyncio.Event,
        model: str | None = None,
        system_prompt: str | None = None,
    ):
        raise AssertionError("native tool provider should use chat_completion, not run()")
        yield  # pragma: no cover

    async def chat_completion(
        self,
        *,
        messages: list[dict],
        model: str | None,
        tools: list[dict] | None = None,
        tool_choice: str | dict | None = None,
    ) -> dict:
        del model, tool_choice
        self.messages.append([dict(message) for message in messages])
        self.tool_payloads.append([dict(tool) for tool in tools] if tools else None)
        response = self.responses[self._index]
        self._index += 1
        return response

    async def describe(self) -> dict:
        return {
            "id": self.name,
            "displayName": self.display_name,
            "available": True,
            "capabilities": {
                "chat": True,
                "streaming": True,
                "toolCalls": True,
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
        follow_up='{"state":"FINAL_CANDIDATE","answer":"Used the file result to answer.","evidence":["README.md"],"done_conditions_met":[],"remaining_uncertainty":[]}',
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
        follow_up='{"state":"FINAL_CANDIDATE","answer":"The tool was blocked, so I cannot inspect that path.","evidence":[],"done_conditions_met":[],"remaining_uncertainty":["Requested path escaped workdir."]}',
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
            '{"state":"FINAL_CANDIDATE","answer":"The repository contains a README and I inspected it successfully.","evidence":["README.md"],"done_conditions_met":["grounded evidence"],"remaining_uncertainty":[]}',
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
    assert "Current contract:" in provider.prompts[0]
    assert "- Required evidence:" in provider.prompts[0]
    assert "directory listing alone is rarely enough" in provider.prompts[0]
    assert "plain files.list result usually is not enough evidence to stop" in provider.prompts[1]


@pytest.mark.asyncio
async def test_harness_follow_up_prompt_demands_grounding_before_repo_summary(tmp_path: Path) -> None:
    provider = SequencedPromptProvider(
        outputs=[
            '{"tool_id":"files.list","arguments":{"path":"."}}',
            '{"state":"FINAL_CANDIDATE","answer":"Grounded answer.","evidence":[],"done_conditions_met":[],"remaining_uncertainty":["Need a cited file."]}',
            '{"tool_id":"files.read","arguments":{"path":"README.md"}}',
            '{"state":"FINAL_CANDIDATE","answer":"README.md explains the architecture and setup path.","evidence":["README.md"],"done_conditions_met":["grounded file evidence","file path citation"],"remaining_uncertainty":[]}',
        ],
    )
    harness = ChatHarness()

    async def tool_executor(request: ToolExecutionRequest, context: ToolExecutionContext) -> ToolExecutionResult:
        if request.tool_id == "files.read":
            return ToolExecutionResult(
                tool_id=request.tool_id,
                ok=True,
                summary="read",
                output={"path": "README.md", "content": "CopeNet setup"},
                body={"path": "README.md", "content": "CopeNet setup"},
            )
        return ToolExecutionResult(tool_id=request.tool_id, ok=True, summary="ok", output={"entries": []}, body={"entries": []})

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
    _, stream = await harness.run_turn(
        provider=provider,
        prompt="Use tools to explain the architecture and setup path for CopeNet.",
        provider_session_id=None,
        abort_event=asyncio.Event(),
        available_tools=ToolRegistry().list_tools(),
        tool_executor=tool_executor,
        tool_context=tool_context,
    )

    [event async for event in stream]

    assert "Before answering a repository-architecture or setup question" in provider.prompts[1]
    assert "cite the specific files you inspected" in provider.prompts[1]


@pytest.mark.asyncio
async def test_harness_native_tool_loop_executes_provider_tool_calls(tmp_path: Path) -> None:
    provider = NativeToolProvider(
        responses=[
            {
                "choices": [
                    {
                        "finish_reason": "tool_calls",
                        "message": {
                            "role": "assistant",
                            "content": "",
                            "tool_calls": [
                                {
                                    "id": "call-1",
                                    "type": "function",
                                    "function": {
                                        "name": "files.read",
                                        "arguments": '{"path":"README.md"}',
                                    },
                                }
                            ],
                        },
                    }
                ]
            },
            {
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "role": "assistant",
                            "content": "README.md describes CopeNet as a local-first agent operator studio.",
                        },
                    }
                ]
            },
        ]
    )
    harness = ChatHarness()

    async def tool_executor(request: ToolExecutionRequest, context: ToolExecutionContext) -> ToolExecutionResult:
        del context
        return ToolExecutionResult(
            tool_id=request.tool_id,
            ok=True,
            summary="Read file README.md.",
            output={"path": "README.md", "content": "CopeNet is a local-first agent operator studio."},
            body={"path": "README.md", "content": "CopeNet is a local-first agent operator studio."},
        )

    tool_context = ToolExecutionContext(
        workdir=tmp_path,
        session_key=None,
        provider_name="lm-studio",
        model=None,
        session_store=SessionStore(path=tmp_path / "index.json"),
        transcript_store=TranscriptStore(root_dir=tmp_path / "history"),
        providers={"lm-studio": provider},
        policy=ToolPolicy(),
        trace=None,
    )
    plan, stream = await harness.run_turn(
        provider=provider,
        prompt="Use tools to explain the architecture and setup path for CopeNet.",
        provider_session_id=None,
        abort_event=asyncio.Event(),
        available_tools=ToolRegistry().list_tools(),
        tool_executor=tool_executor,
        tool_context=tool_context,
    )

    events = [event async for event in stream]

    assert plan.tool_execution_mode == "native"
    assert provider.tool_payloads[0]
    assert any(tool["function"]["name"] == "files.read" for tool in provider.tool_payloads[0])
    meta_event = next(event for event in events if event.kind == "meta")
    assert meta_event.metadata["toolExecution"]["toolId"] == "files.read"
    final_text = "".join(event.text or "" for event in events if event.kind == "delta")
    assert "README.md" in final_text
    tool_message = provider.messages[1][-1]
    assert tool_message["role"] == "tool"
    assert tool_message["tool_call_id"] == "call-1"


@pytest.mark.asyncio
async def test_harness_native_final_gate_rejects_ungrounded_answer_and_forces_follow_up(tmp_path: Path) -> None:
    provider = NativeToolProvider(
        responses=[
            {
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "role": "assistant",
                            "content": "The repo keeps its main logic in src/copenet.",
                        },
                    }
                ]
            },
            {
                "choices": [
                    {
                        "finish_reason": "tool_calls",
                        "message": {
                            "role": "assistant",
                            "content": "",
                            "tool_calls": [
                                {
                                    "id": "call-2",
                                    "type": "function",
                                    "function": {
                                        "name": "files.read",
                                        "arguments": '{"path":"README.md"}',
                                    },
                                }
                            ],
                        },
                    }
                ]
            },
            {
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "role": "assistant",
                            "content": "README.md describes CopeNet as a local-first agent operator studio.",
                        },
                    }
                ]
            },
        ]
    )
    harness = ChatHarness()

    async def tool_executor(request: ToolExecutionRequest, context: ToolExecutionContext) -> ToolExecutionResult:
        del context
        return ToolExecutionResult(
            tool_id=request.tool_id,
            ok=True,
            summary="Read file README.md.",
            output={"path": "README.md", "content": "CopeNet is a local-first agent operator studio."},
            body={"path": "README.md", "content": "CopeNet is a local-first agent operator studio."},
        )

    tool_context = ToolExecutionContext(
        workdir=tmp_path,
        session_key=None,
        provider_name="lm-studio",
        model=None,
        session_store=SessionStore(path=tmp_path / "index.json"),
        transcript_store=TranscriptStore(root_dir=tmp_path / "history"),
        providers={"lm-studio": provider},
        policy=ToolPolicy(),
        trace=None,
    )
    _, stream = await harness.run_turn(
        provider=provider,
        prompt="Use tools to explain the architecture and setup path for CopeNet.",
        provider_session_id=None,
        abort_event=asyncio.Event(),
        available_tools=ToolRegistry().list_tools(),
        tool_executor=tool_executor,
        tool_context=tool_context,
    )
    events = [event async for event in stream]

    assert any(message[-1]["role"] == "user" and "Missing requirements" in message[-1]["content"] for message in provider.messages[1:])
    final_text = "".join(event.text or "" for event in events if event.kind == "delta")
    assert "README.md" in final_text


@pytest.mark.asyncio
async def test_native_step_exhaustion_forces_terminal_answer(tmp_path: Path) -> None:
    provider = NativeToolProvider(
        responses=[
            {
                "choices": [
                    {
                        "finish_reason": "tool_calls",
                        "message": {
                            "role": "assistant",
                            "content": "",
                            "tool_calls": [
                                {
                                    "id": f"call-{index}",
                                    "type": "function",
                                    "function": {
                                        "name": "files.list",
                                        "arguments": '{"path":"."}',
                                    },
                                }
                            ],
                        },
                    }
                ]
            }
            for index in range(1, 5)
        ]
        + [
            {
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "role": "assistant",
                            "content": "After repeated listing, the repository root contains the expected project files.",
                        },
                    }
                ]
            }
        ]
    )
    traces: list[tuple[str, dict | None]] = []
    harness = ChatHarness()

    def trace(event: str, payload: dict | None = None) -> None:
        traces.append((event, payload))

    async def tool_executor(request: ToolExecutionRequest, context: ToolExecutionContext) -> ToolExecutionResult:
        del context
        return ToolExecutionResult(
            tool_id=request.tool_id,
            ok=True,
            summary="Listed root.",
            output={"entries": [{"path": "README.md"}]},
            body={"entries": [{"path": "README.md"}]},
        )

    tool_context = ToolExecutionContext(
        workdir=tmp_path,
        session_key=None,
        provider_name="lm-studio",
        model=None,
        session_store=SessionStore(path=tmp_path / "index.json"),
        transcript_store=TranscriptStore(root_dir=tmp_path / "history"),
        providers={"lm-studio": provider},
        policy=ToolPolicy(),
        trace=trace,
    )
    _, stream = await harness.run_turn(
        provider=provider,
        prompt="Use tools to inspect the repository and summarize what you found.",
        provider_session_id=None,
        abort_event=asyncio.Event(),
        available_tools=ToolRegistry().list_tools(),
        tool_executor=tool_executor,
        tool_context=tool_context,
        trace=trace,
    )

    events = [event async for event in stream]

    final_text = "".join(event.text or "" for event in events if event.kind == "delta")
    assert "repository root contains the expected project files" in final_text
    assert any(event == "terminal_answer_forced_after_max_turns" for event, _ in traces)


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
            '{"tool_id":"shell.exec","arguments":{"command":"pwd"}}'
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
    blocked_trace = next(payload for event, payload in traces if event == "tool_blocked")
    assert blocked_trace is not None
    assert blocked_trace["toolId"] == "tool.batch"
    assert blocked_trace["step"] == 1
    assert "shell.exec" in blocked_trace["rawText"]


@pytest.mark.asyncio
async def test_harness_allows_safe_batch_with_context_prepare(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Temp Repo\nHello\n", encoding="utf-8")
    provider = PromptedBatchProvider(
        tool_json=(
            '{"tool_calls":['
            '{"tool_id":"files.list","arguments":{"path":"."}},'
            '{"tool_id":"context.prepare","arguments":{"query":"inspect runtime"}}'
            ']}'
        ),
        follow_up="Used the list plus prepared context to answer.",
    )
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
        trace=None,
    )
    _, stream = await harness.run_turn(
        provider=provider,
        prompt="Inspect the repo",
        provider_session_id=None,
        abort_event=asyncio.Event(),
        available_tools=registry.list_tools(),
        tool_executor=registry.execute,
        tool_context=tool_context,
    )
    events = [event async for event in stream]

    meta_event = next(event for event in events if event.kind == "meta")
    assert meta_event.metadata["toolExecution"]["toolId"] == "tool.batch"
    assert meta_event.metadata["toolExecution"]["ok"] is True


@pytest.mark.asyncio
async def test_harness_generates_correction_result_for_malformed_tool_request(tmp_path: Path) -> None:
    provider = PromptedBatchProvider(
        tool_json='{"tool_id":"files.read","arguments":"README.md"}',
        follow_up="I repaired the tool call and can answer now.",
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
    assert meta_event.metadata["toolExecution"]["toolId"] == "tool.parse"
    assert meta_event.metadata["toolExecution"]["ok"] is False
    assert meta_event.metadata["turnState"]["transitionReason"] == "tool_error_correction"
    assert any(event == "tool_correction_generated" for event, _ in traces)


@pytest.mark.asyncio
async def test_harness_rejects_freeform_final_and_requests_structured_action(tmp_path: Path) -> None:
    provider = PromptedBatchProvider(
        tool_json='I inspected the repo and it looks fine.',
        follow_up='{"state":"FINAL_CANDIDATE","answer":"I inspected README.md.","evidence":["README.md"],"done_conditions_met":["grounded evidence"],"remaining_uncertainty":[]}',
    )
    traces: list[tuple[str, dict | None]] = []

    def trace(event: str, payload: dict | None = None) -> None:
        traces.append((event, payload))

    harness = ChatHarness()

    async def tool_executor(request: ToolExecutionRequest, context: ToolExecutionContext) -> ToolExecutionResult:
        return ToolExecutionResult(
            tool_id=request.tool_id,
            ok=True,
            summary="Read file README.md.",
            output={"path": "README.md", "content": "CopeNet"},
            body={"path": "README.md", "content": "CopeNet"},
        )

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
        available_tools=ToolRegistry().list_tools(),
        tool_executor=tool_executor,
        tool_context=tool_context,
        trace=trace,
    )
    events = [event async for event in stream]

    meta_event = next(event for event in events if event.kind == "meta")
    assert meta_event.metadata["toolExecution"]["toolId"] == "tool.parse"
    assert meta_event.metadata["toolExecution"]["ok"] is False
    assert "FINAL_CANDIDATE" in meta_event.metadata["toolExecution"]["error"]
    assert any(event == "tool_correction_generated" for event, _ in traces)


@pytest.mark.asyncio
async def test_harness_persists_oversized_tool_output_as_artifact(tmp_path: Path) -> None:
    provider = PromptedToolProvider(
        tool_json='{"tool_id":"files.read","arguments":{"path":"README.md"}}',
        follow_up="Used the persisted artifact preview to answer.",
    )
    traces: list[tuple[str, dict | None]] = []

    def trace(event: str, payload: dict | None = None) -> None:
        traces.append((event, payload))

    harness = ChatHarness()

    async def tool_executor(request: ToolExecutionRequest, context: ToolExecutionContext) -> ToolExecutionResult:
        return ToolExecutionResult(
            tool_id=request.tool_id,
            ok=True,
            summary="Read README.md.",
            output={"content": "X" * 5000},
            body={"content": "X" * 5000},
        )

    artifact_store = ArtifactStore(root_dir=tmp_path / "artifacts")
    tool_context = ToolExecutionContext(
        workdir=tmp_path,
        session_key="alpha",
        provider_name="prompted",
        model=None,
        session_store=SessionStore(path=tmp_path / "index.json"),
        transcript_store=TranscriptStore(root_dir=tmp_path / "history"),
        providers={"prompted": provider},
        policy=ToolPolicy(),
        artifact_store=artifact_store,
        trace=trace,
    )
    _, stream = await harness.run_turn(
        provider=provider,
        prompt="Read the README",
        provider_session_id=None,
        abort_event=asyncio.Event(),
        available_tools=ToolRegistry().list_tools(),
        tool_executor=tool_executor,
        tool_context=tool_context,
        trace=trace,
    )
    events = [event async for event in stream]

    meta_event = next(event for event in events if event.kind == "meta")
    assert meta_event.metadata["toolResult"]["artifactId"]
    artifacts = artifact_store.list_for_session("alpha")
    assert artifacts
    assert artifacts[0].type == "tool_output"
    assert any(event == "tool_result_persisted" for event, _ in traces)


@pytest.mark.asyncio
async def test_orchestrator_tool_loop_surfaces_directory_guidance_for_files_read(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("COPNET_WORKDIR", str(tmp_path))
    (tmp_path / "src").mkdir()
    provider = PromptedToolProvider(
        tool_json='{"tool_id":"files.read","arguments":{"path":"src"}}',
        follow_up='{"state":"FINAL_CANDIDATE","answer":"That path is a directory, so I should use files.list instead.","evidence":[],"done_conditions_met":[],"remaining_uncertainty":["files.read cannot inspect directories."]}',
    )
    orchestrator = Orchestrator(
        session_store=SessionStore(path=tmp_path / "index.json"),
        transcript_store=TranscriptStore(root_dir=tmp_path),
        sessions_dir=tmp_path,
        providers={"prompted": provider},
    )

    _, events = await _collect(
        orchestrator,
        ChatSendRequest(session_key="alpha", message="Inspect src", provider="prompted"),
    )

    final_event = events[-1]
    assert final_event["toolExecution"]["toolId"] == "files.read"
    assert final_event["toolExecution"]["ok"] is False
    assert "path is a directory" in final_event["toolExecution"]["error"]
    assert "use files.list to inspect directories" in final_event["toolExecution"]["error"]


@pytest.mark.asyncio
async def test_orchestrator_tool_loop_blocks_shell_pipelines_with_actionable_error(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("COPNET_WORKDIR", str(tmp_path))
    provider = PromptedToolProvider(
        tool_json='{"tool_id":"shell.exec","arguments":{"command":"rg session | head"}}',
        follow_up='{"state":"FINAL_CANDIDATE","answer":"The shell command was blocked, so I should use files.search or a simpler command.","evidence":[],"done_conditions_met":[],"remaining_uncertainty":["Pipelines are blocked by policy."]}',
    )
    orchestrator = Orchestrator(
        session_store=SessionStore(path=tmp_path / "index.json"),
        transcript_store=TranscriptStore(root_dir=tmp_path),
        sessions_dir=tmp_path,
        providers={"prompted": provider},
    )

    _, events = await _collect(
        orchestrator,
        ChatSendRequest(session_key="alpha", message="Search for session references", provider="prompted"),
    )

    final_event = events[-1]
    assert final_event["toolExecution"]["toolId"] == "shell.exec"
    assert final_event["toolExecution"]["ok"] is False
    assert "do not use pipes, chaining, or redirection" in final_event["toolExecution"]["error"]


@pytest.mark.asyncio
async def test_harness_final_gate_rejects_listing_only_answer_and_forces_follow_up(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Temp Repo\nHello\n", encoding="utf-8")
    provider = SequencedPromptProvider(
        outputs=[
            '{"tool_id":"files.list","arguments":{"path":"."}}',
            '{"state":"FINAL_CANDIDATE","answer":"The repo keeps its main logic in src/copenet.","evidence":[],"done_conditions_met":[],"remaining_uncertainty":["Need grounding."]}',
            '{"tool_id":"files.read","arguments":{"path":"README.md"}}',
            '{"state":"FINAL_CANDIDATE","answer":"README.md says the repo is a local-first agent operator studio.","evidence":["README.md"],"done_conditions_met":["grounded file evidence","file path citation"],"remaining_uncertainty":[]}',
        ],
    )
    harness = ChatHarness()
    tool_calls: list[ToolExecutionRequest] = []

    async def tool_executor(request: ToolExecutionRequest, context: ToolExecutionContext) -> ToolExecutionResult:
        tool_calls.append(request)
        if request.tool_id == "files.read":
            return ToolExecutionResult(
                tool_id=request.tool_id,
                ok=True,
                summary="Read file README.md.",
                output={"path": "README.md", "content": "CopeNet is a local-first agent operator studio."},
                body={"path": "README.md", "content": "CopeNet is a local-first agent operator studio."},
            )
        return ToolExecutionResult(
            tool_id=request.tool_id,
            ok=True,
            summary="Listed root.",
            output={"entries": [{"path": "README.md", "isDir": False}]},
            body={"entries": [{"path": "README.md", "isDir": False}]},
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
    _, stream = await harness.run_turn(
        provider=provider,
        prompt="Use tools to explain the architecture and setup path for CopeNet.",
        provider_session_id=None,
        abort_event=asyncio.Event(),
        available_tools=ToolRegistry().list_tools(),
        tool_executor=tool_executor,
        tool_context=tool_context,
    )

    events = [event async for event in stream]

    assert [call.tool_id for call in tool_calls] == ["files.list", "files.read"]
    assert any("Missing requirements:" in prompt for prompt in provider.prompts)
    final_text = "".join(event.text or "" for event in events if event.kind == "delta")
    assert "README.md" in final_text


@pytest.mark.asyncio
async def test_harness_plan_filters_shell_exec_for_patch_plan_prompt(tmp_path: Path) -> None:
    provider = PromptedToolProvider(tool_json='{"tool_id":"files.list","arguments":{"path":"."}}')
    harness = ChatHarness()

    plan = await harness.plan_turn(
        provider=provider,
        provider_name="prompted",
        model=None,
        available_tools=ToolRegistry().list_tools(),
        prompt="Use tools to inspect the runtime code and produce a small patch plan for improving repository exploration behavior with smaller models.",
    )

    assert plan.task_contract.task_kind == "patch_plan"
    assert all(tool.id != "shell.exec" for tool in plan.tools)
