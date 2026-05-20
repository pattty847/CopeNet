import asyncio
from pathlib import Path

import pytest

from copenet.core.harness import ChatHarness
from copenet.core.orchestrator import ChatSendRequest, Orchestrator
from copenet.core.sessions import SessionStore, TranscriptStore
from copenet.core.tools import ToolExecutionContext, ToolExecutionRequest, ToolExecutionResult, ToolPolicy, ToolRegistry
from copenet.providers import ProviderEvent


class PromptedProvider:
    name = "prompted"
    display_name = "Prompted"

    def __init__(self, text: str | list[str]) -> None:
        self.responses = [text] if isinstance(text, str) else list(text)
        self.prompts: list[str] = []

    async def run(
        self,
        prompt: str,
        provider_session_id: str | None,
        abort_event: asyncio.Event,
        model: str | None = None,
        system_prompt: str | None = None,
    ):
        del abort_event, model, system_prompt
        self.prompts.append(prompt)
        index = min(len(self.prompts) - 1, len(self.responses) - 1)
        yield ProviderEvent(kind="delta", text=self.responses[index], provider_session_id=provider_session_id or "provider-session")
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


class CliProvider(PromptedProvider):
    name = "codex-cli"
    display_name = "Codex CLI"

    async def describe(self) -> dict:
        return {
            "id": self.name,
            "displayName": self.display_name,
            "available": True,
            "capabilities": {
                "chat": True,
                "streaming": True,
                "toolCalls": False,
                "promptedToolUse": False,
                "resume": True,
            },
        }


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
async def test_orchestrator_runs_prompted_json_tool_loop(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("COPNET_WORKDIR", str(tmp_path))
    (tmp_path / "README.md").write_text("# Temp Repo\nHello\n", encoding="utf-8")
    provider = PromptedProvider([
        '{"tool_id":"files.read","arguments":{"path":"README.md"}}',
        "I read the README and found Temp Repo.",
    ])
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
    assert final_event["message"]["content"] == "I read the README and found Temp Repo."
    assert final_event["toolExecution"]["toolId"] == "files.read"
    assert [event["state"] for event in events] == ["tool_called", "tool_result", "delta", "final"]
    assert len(provider.prompts) == 2


@pytest.mark.asyncio
async def test_harness_native_tool_loop_executes_provider_tool_call_then_plain_text(tmp_path: Path) -> None:
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
                            "content": "README.md describes CopeNet as a local agent gateway.",
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
            output={"path": "README.md", "content": "CopeNet is a local agent gateway."},
            body={"path": "README.md", "content": "CopeNet is a local agent gateway."},
        )

    tool_context = ToolExecutionContext(
        workdir=tmp_path,
        session_workspace_root=tmp_path,
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
        prompt="Use tools to explain CopeNet.",
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
    assert [message["role"] for message in provider.messages[1]] == ["system", "user", "assistant", "tool"]
    meta_event = next(event for event in events if event.kind == "meta" and "toolExecution" in (event.metadata or {}))
    assert meta_event.metadata["toolExecution"]["toolId"] == "files.read"
    final_text = "".join(event.text or "" for event in events if event.kind == "delta")
    assert final_text == "README.md describes CopeNet as a local agent gateway."


@pytest.mark.asyncio
async def test_harness_prompted_provider_executes_json_tool_requests(tmp_path: Path) -> None:
    provider = PromptedProvider([
        '{"command":"pwd","timeout":120000}',
        "The command returned the workspace path.",
    ])
    harness = ChatHarness()
    tool_context = ToolExecutionContext(
        workdir=tmp_path,
        session_workspace_root=tmp_path,
        session_key=None,
        provider_name="prompted",
        model=None,
        session_store=SessionStore(path=tmp_path / "index.json"),
        transcript_store=TranscriptStore(root_dir=tmp_path / "history"),
        providers={"prompted": provider},
        policy=ToolPolicy(),
        trace=None,
    )

    executed: list[ToolExecutionRequest] = []

    async def tool_executor(request: ToolExecutionRequest, context: ToolExecutionContext) -> ToolExecutionResult:
        del context
        executed.append(request)
        return ToolExecutionResult(
            tool_id=request.tool_id,
            ok=True,
            summary="Ran shell command: pwd",
            output={"command": "pwd", "stdout": str(tmp_path), "stderr": "", "exitCode": 0},
        )

    plan, stream = await harness.run_turn(
        provider=provider,
        prompt="Run pwd",
        provider_session_id=None,
        abort_event=asyncio.Event(),
        available_tools=ToolRegistry().list_tools(),
        tool_executor=tool_executor,
        tool_context=tool_context,
    )

    events = [event async for event in stream]
    final_text = "".join(event.text or "" for event in events if event.kind == "delta")

    assert plan.tool_execution_mode == "prompted"
    assert len(provider.prompts) == 2
    assert executed[0].tool_id == "shell.exec"
    assert executed[0].arguments == {"command": "pwd"}
    assert any(event.kind == "meta" and "toolExecution" in (event.metadata or {}) for event in events)
    assert final_text == "The command returned the workspace path."


@pytest.mark.asyncio
async def test_cli_provider_passthrough_even_when_tools_exist(tmp_path: Path) -> None:
    provider = CliProvider("Plain CLI answer.")
    harness = ChatHarness()
    tool_context = ToolExecutionContext(
        workdir=tmp_path,
        session_workspace_root=tmp_path,
        session_key=None,
        provider_name="codex-cli",
        model=None,
        session_store=SessionStore(path=tmp_path / "index.json"),
        transcript_store=TranscriptStore(root_dir=tmp_path / "history"),
        providers={"codex-cli": provider},
        policy=ToolPolicy(),
        trace=None,
    )

    async def tool_executor(request: ToolExecutionRequest, context: ToolExecutionContext) -> ToolExecutionResult:
        raise AssertionError(f"CLI provider should not execute {request.tool_id}")

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

    assert plan.will_attempt_tool_loop is False
    assert [event.text for event in events if event.kind == "delta"] == ["Plain CLI answer."]
