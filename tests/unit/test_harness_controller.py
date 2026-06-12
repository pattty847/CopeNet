from __future__ import annotations

import pytest

from copenet.core.harness.planning import plan_turn
from copenet.core.runtime.turn_state import TurnState
from copenet.core.sessions import SessionStore, TranscriptStore
from copenet.core.tools import (
    ToolDescriptor,
    ToolExecutionContext,
    ToolExecutionRequest,
    ToolExecutionResult,
    ToolPolicy,
    ToolRegistry,
)


class PromptedProvider:
    name = "prompted"
    display_name = "Prompted"

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
    name = "native"
    display_name = "Native"

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


class CodexLikeProvider:
    name = "codex-cli"
    display_name = "Codex"

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

    async def list_models(self) -> list:
        return []


def _policy_visible_tools() -> list[ToolDescriptor]:
    policy = ToolPolicy()
    return [tool for tool in ToolRegistry().list_tools() if tool.category in policy.allowed_categories]


@pytest.mark.asyncio
async def test_plan_turn_keeps_policy_visible_tools_without_prompt_classification() -> None:
    provider = PromptedProvider()

    plan = await plan_turn(
        provider=provider,
        provider_name="prompted",
        model="local-model",
        available_tools=_policy_visible_tools(),
        prompt="Hey, quick question - how is auth wired in this repo?",
    )

    visible_ids = {tool.id for tool in plan.tools}
    # Phase 3: the model-facing manifest is the five primitives; the read-only
    # subset visible under the default policy is files.read / files.rg / shell.exec.
    assert {"files.rg", "files.read"}.issubset(visible_ids)
    assert "repo.map" not in visible_ids
    assert "test.discover" not in visible_ids
    assert "patch.plan" not in visible_ids
    assert "tools.describe" not in visible_ids
    assert not hasattr(plan, "soft_posture")
    assert not hasattr(plan, "interaction_class")
    assert not hasattr(plan, "task_contract")


@pytest.mark.asyncio
async def test_plan_turn_uses_native_tool_loop_only_when_provider_supports_tool_calls() -> None:
    provider = NativeToolProvider()

    plan = await plan_turn(
        provider=provider,
        provider_name="native",
        model="local-model",
        available_tools=ToolRegistry().list_tools(),
        prompt="Please write a short haiku about fresh bread and quiet mornings.",
    )

    assert plan.will_attempt_tool_loop is True
    assert plan.tool_execution_mode == "native"


@pytest.mark.asyncio
async def test_plan_turn_uses_prompted_tool_loop_when_provider_supports_prompted_tools() -> None:
    provider = PromptedProvider()

    plan = await plan_turn(
        provider=provider,
        provider_name="prompted",
        model="local-model",
        available_tools=ToolRegistry().list_tools(),
        prompt="Inspect the repository if you can.",
    )

    assert plan.will_attempt_tool_loop is True
    assert plan.tool_execution_mode == "prompted"


@pytest.mark.asyncio
async def test_plan_turn_does_not_attempt_tool_loop_for_opaque_codex_provider() -> None:
    provider = CodexLikeProvider()

    plan = await plan_turn(
        provider=provider,
        provider_name="codex-cli",
        model="gpt-5.4",
        available_tools=ToolRegistry().list_tools(),
        prompt="Explain the repository architecture with grounded evidence.",
    )

    assert plan.will_attempt_tool_loop is False
    assert plan.tool_execution_mode == "none"


def test_turn_state_records_evidence_categories() -> None:
    state = TurnState()

    state.record_tool_step(
        tool_id="shell.exec",
        arguments={"command": "ls ."},
        result=ToolExecutionResult(
            tool_id="shell.exec",
            ok=True,
            summary="Listed root.",
            output={"stdout": "README.md\nsrc/"},
        ),
    )
    state.record_tool_step(
        tool_id="files.rg",
        arguments={"pattern": "runtime", "path": "."},
        result=ToolExecutionResult(
            tool_id="files.rg",
            ok=True,
            summary="Found runtime matches.",
            output={"matches": [{"path": "src/copenet/core/harness/tool_loop.py", "line": 1, "text": "runtime"}]},
            body={"matches": [{"path": "src/copenet/core/harness/tool_loop.py", "line": 1, "text": "runtime"}]},
        ),
    )
    state.record_tool_step(
        tool_id="files.read",
        arguments={"path": "README.md"},
        result=ToolExecutionResult(
            tool_id="files.read",
            ok=True,
            summary="Read README.md.",
            output={"path": "README.md", "content": "hello"},
            body={"path": "README.md", "content": "hello"},
        ),
    )

    assert state.visited_tools == ["shell.exec", "files.rg", "files.read"]
    assert "src/copenet/core/harness/tool_loop.py" in state.visited_paths
    assert state.grounding_actions == ["files.read"]
    assert [item["category"] for item in state.evidence_items] == ["reconnaissance", "directional", "grounding"]
    assert state.last_tool_result_summary == "Read README.md."


@pytest.mark.asyncio
async def test_tool_registry_warns_then_blocks_repeated_identical_files_read(tmp_path) -> None:
    (tmp_path / "README.md").write_text("hello")
    registry = ToolRegistry()
    context = ToolExecutionContext(
        workdir=tmp_path,
        session_workspace_root=tmp_path,
        session_key=None,
        provider_name="prompted",
        model=None,
        session_store=SessionStore(path=tmp_path / "index.json"),
        transcript_store=TranscriptStore(root_dir=tmp_path / "history"),
        providers={},
        policy=registry.policy,
        trace=None,
    )
    request = ToolExecutionRequest(tool_id="files.read", arguments={"path": "README.md"})

    results = [await registry.execute(request, context) for _ in range(4)]

    assert results[2].ok is True
    assert "You have read the same file repeatedly" in results[2].summary
    assert results[3].ok is False
    assert "Blocked repeated identical files.read call" in (results[3].error or "")
