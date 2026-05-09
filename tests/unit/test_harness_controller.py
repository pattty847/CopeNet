from __future__ import annotations

import asyncio

import pytest

from copenet.core.harness.final_gate import final_gate_evaluate
from copenet.core.harness.planning import plan_turn
from copenet.core.sessions import SessionStore, TranscriptStore
from copenet.core.runtime.turn_state import TurnState
from copenet.core.tools import FinalCandidateEnvelope, ToolDescriptor, ToolExecutionContext, ToolExecutionRequest, ToolExecutionResult, ToolRegistry


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


@pytest.mark.asyncio
async def test_plan_turn_attaches_patch_plan_contract_and_filters_shell_exec() -> None:
    provider = PromptedProvider()

    plan = await plan_turn(
        provider=provider,
        provider_name="prompted",
        model="local-model",
        available_tools=ToolRegistry().list_tools(),
        prompt="Use tools to inspect the runtime code and produce a small patch plan for improving repository exploration behavior with smaller models.",
    )

    assert plan.interaction_class == "agent"
    assert plan.task_contract.task_kind == "patch_plan"
    assert "shell.exec" not in plan.task_contract.allowed_tools
    assert all(tool.id != "shell.exec" for tool in plan.tools)
    assert plan.task_contract.preferred_next_actions[:2] == ["files.rg", "files.read"]


@pytest.mark.asyncio
async def test_plan_turn_prefers_native_tool_calls_over_prompted_loop() -> None:
    provider = NativeToolProvider()

    plan = await plan_turn(
        provider=provider,
        provider_name="native",
        model="local-model",
        available_tools=ToolRegistry().list_tools(),
        prompt="Explain the repository architecture with grounded evidence.",
    )

    assert plan.interaction_class == "agent"
    assert plan.will_attempt_tool_loop is True
    assert plan.tool_execution_mode == "native"
    assert plan.batch_read_allowed is False


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

    assert plan.interaction_class == "agent"
    assert plan.will_attempt_tool_loop is False
    assert plan.tool_execution_mode == "none"
    assert plan.tool_loop_suppressed_reason == "provider_tool_loop_unavailable"


@pytest.mark.asyncio
async def test_plan_turn_ignores_generic_writing_prompt_without_repo_context() -> None:
    provider = PromptedProvider()

    plan = await plan_turn(
        provider=provider,
        provider_name="prompted",
        model="local-model",
        available_tools=ToolRegistry().list_tools(),
        prompt="Please write a short haiku about fresh bread and quiet mornings.",
    )

    assert plan.interaction_class == "casual"
    assert plan.task_contract is None


@pytest.mark.asyncio
async def test_plan_turn_detects_file_workflow_without_matching_bread_or_checkout_noise() -> None:
    provider = PromptedProvider()

    plan = await plan_turn(
        provider=provider,
        provider_name="prompted",
        model="local-model",
        available_tools=ToolRegistry().list_tools(),
        prompt="Read docs/tests/TEST_FILE.md, edit it, and run ls docs/tests after the change.",
    )

    assert plan.task_contract is not None
    assert plan.interaction_class == "agent"
    assert plan.task_contract.task_kind == "patch_apply_verify"
    assert "files.edit" in plan.task_contract.allowed_tools
    assert "shell.exec" in plan.task_contract.allowed_tools


@pytest.mark.asyncio
async def test_plan_turn_keeps_soft_harness_feedback_conversational() -> None:
    provider = PromptedProvider()

    plan = await plan_turn(
        provider=provider,
        provider_name="prompted",
        model="local-model",
        available_tools=ToolRegistry().list_tools(),
        prompt="What do you think of this harness direction? I want it to feel less protocol-y and more like a friend with a workshop.",
    )

    assert plan.interaction_class == "advisory"
    assert plan.prompt_frame == "light"
    assert plan.task_contract is None
    assert plan.will_attempt_tool_loop is False
    assert plan.tool_loop_suppressed_reason == "interaction_class_advisory"


@pytest.mark.asyncio
async def test_plan_turn_marks_destructive_requests_as_risky() -> None:
    provider = PromptedProvider()

    plan = await plan_turn(
        provider=provider,
        provider_name="prompted",
        model="local-model",
        available_tools=ToolRegistry().list_tools(),
        prompt="Reset the repo, delete the old snapshots, and push the cleanup branch.",
    )

    assert plan.interaction_class == "risky"
    assert plan.prompt_frame == "full"


def test_turn_state_records_evidence_categories() -> None:
    state = TurnState()

    state.record_tool_step(
        tool_id="files.list",
        arguments={"path": "."},
        result=ToolExecutionResult(tool_id="files.list", ok=True, summary="Listed root.", output={"entries": [{"path": "README.md"}]}, body={"entries": [{"path": "README.md"}]})
    )
    state.record_tool_step(
        tool_id="files.search",
        arguments={"pattern": "runtime", "path": "."},
        result=ToolExecutionResult(tool_id="files.search", ok=True, summary="Found runtime matches.", output={"matches": [{"path": "src/copenet/core/harness/tool_loop.py", "line": 1, "text": "runtime"}]}, body={"matches": [{"path": "src/copenet/core/harness/tool_loop.py", "line": 1, "text": "runtime"}]})
    )
    state.record_tool_step(
        tool_id="files.read",
        arguments={"path": "README.md"},
        result=ToolExecutionResult(tool_id="files.read", ok=True, summary="Read README.md.", output={"path": "README.md", "content": "hello"}, body={"path": "README.md", "content": "hello"})
    )

    assert state.visited_tools == ["files.list", "files.search", "files.read"]
    assert "README.md" in state.visited_paths
    assert "src/copenet/core/harness/tool_loop.py" in state.visited_paths
    assert state.grounding_actions == ["files.read"]
    assert [item["category"] for item in state.evidence_items] == ["reconnaissance", "directional", "grounding"]
    assert state.last_tool_result_summary == "Read README.md."


def test_final_gate_rejects_listing_only_repo_explain() -> None:
    state = TurnState()
    state.record_tool_step(
        tool_id="files.list",
        arguments={"path": "."},
        result=ToolExecutionResult(tool_id="files.list", ok=True, summary="Listed root.", output={"entries": [{"path": "README.md"}]}, body={"entries": [{"path": "README.md"}]})
    )

    contract = {
        "taskKind": "repo_explain",
        "goal": "Explain the repository architecture.",
        "doneConditions": ["grounded file evidence", "file path citation"],
    }
    decision = final_gate_evaluate(
        contract=contract,
        turn_state=state,
        candidate=FinalCandidateEnvelope(answer="The repo keeps the main logic in src/copenet."),
    )

    assert decision.ok is False
    assert decision.reason_code == "missing_file_evidence"
    assert "grounded file evidence" in " ".join(decision.missing_requirements)


def test_final_gate_rejects_context_only_repo_explain() -> None:
    state = TurnState()
    state.record_tool_step(
        tool_id="context.prepare",
        arguments={"query": "repo overview"},
        result=ToolExecutionResult(
            tool_id="context.prepare",
            ok=True,
            summary="Prepared session and repo context.",
            output={"workdir": "."},
            body={"workdir": "."},
        ),
    )

    contract = {
        "taskKind": "repo_explain",
        "goal": "Explain the repository architecture.",
        "doneConditions": ["grounded file evidence", "file path citation"],
    }
    decision = final_gate_evaluate(
        contract=contract,
        turn_state=state,
        candidate=FinalCandidateEnvelope(answer="I have enough context to explain the repo."),
    )

    assert decision.ok is False
    assert decision.reason_code == "contextual_only_evidence"
    assert decision.recommended_next_action_type == "files.search"


def test_final_gate_accepts_grounded_repo_explain_with_cited_file() -> None:
    state = TurnState()
    state.record_tool_step(
        tool_id="files.read",
        arguments={"path": "README.md"},
        result=ToolExecutionResult(tool_id="files.read", ok=True, summary="Read README.md.", output={"path": "README.md", "content": "CopeNet is a local-first agent operator studio."}, body={"path": "README.md", "content": "CopeNet is a local-first agent operator studio."})
    )

    contract = {
        "taskKind": "repo_explain",
        "goal": "Explain the repository architecture.",
        "doneConditions": ["grounded file evidence", "file path citation"],
    }
    decision = final_gate_evaluate(
        contract=contract,
        turn_state=state,
        candidate=FinalCandidateEnvelope(answer="README.md describes CopeNet as a local-first agent operator studio.", evidence=["README.md"]),
    )

    assert decision.ok is True
    assert decision.reason_code is None


def test_final_gate_requires_verification_for_patch_apply_verify() -> None:
    state = TurnState()
    state.record_tool_step(
        tool_id="files.read",
        arguments={"path": "src/copenet/core/harness/tool_loop.py"},
        result=ToolExecutionResult(tool_id="files.read", ok=True, summary="Read tool_loop.", output={"path": "src/copenet/core/harness/tool_loop.py", "content": "..."}, body={"path": "src/copenet/core/harness/tool_loop.py", "content": "..."})
    )
    state.record_tool_step(
        tool_id="patch.apply",
        arguments={"path": "src/copenet/core/harness/tool_loop.py"},
        result=ToolExecutionResult(tool_id="patch.apply", ok=True, summary="Applied patch.", output={"path": "src/copenet/core/harness/tool_loop.py"}, body={"path": "src/copenet/core/harness/tool_loop.py"})
    )

    contract = {
        "taskKind": "patch_apply_verify",
        "goal": "Patch and verify the harness.",
        "doneConditions": ["patch applied", "verification run"],
    }
    decision = final_gate_evaluate(
        contract=contract,
        turn_state=state,
        candidate=FinalCandidateEnvelope(answer="I applied the fix."),
    )

    assert decision.ok is False
    assert decision.reason_code == "missing_verification"


def test_final_gate_flags_reconnaissance_saturation_after_repeated_listings() -> None:
    state = TurnState()
    for _ in range(2):
        state.record_tool_step(
            tool_id="files.list",
            arguments={"path": "."},
            result=ToolExecutionResult(
                tool_id="files.list",
                ok=True,
                summary="Listed root.",
                output={"entries": [{"path": "README.md"}]},
                body={"entries": [{"path": "README.md"}]},
            ),
        )

    contract = {
        "taskKind": "repo_explain",
        "goal": "Explain the repository architecture.",
        "doneConditions": ["grounded file evidence", "file path citation"],
    }
    decision = final_gate_evaluate(
        contract=contract,
        turn_state=state,
        candidate=FinalCandidateEnvelope(answer="The repo is probably centered around src/copenet."),
    )

    assert decision.ok is False
    assert decision.reason_code == "reconnaissance_saturation"


@pytest.mark.asyncio
async def test_tool_registry_warns_then_blocks_repeated_identical_files_list(tmp_path) -> None:
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
    request = ToolExecutionRequest(tool_id="files.list", arguments={"path": "."})

    results = [await registry.execute(request, context) for _ in range(4)]

    assert results[2].ok is True
    assert "Repeated identical files.list calls are low value" in results[2].summary
    assert results[3].ok is False
    assert "Blocked repeated identical files.list call" in (results[3].error or "")
