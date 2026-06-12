"""Tests for the multi-agent orchestration layer.

Covers the spec's success criteria:
  1. One turn flows through provider selection without blocking.
  2. Fallback chain works (Codex fails -> Claude succeeds).
  3. Trace events are emitted and loggable.
  4. Selection is route-driven and availability-aware.
"""

from __future__ import annotations

import asyncio

import pytest

from copenet.core.multiagent import (
    MultiAgentOrchestrator,
    ProviderRoleMap,
    SubAgentTask,
    build_subagent_prompt,
    delegate_subagent_task,
    execute_with_fallback,
    select_provider_chain,
)


# -- provider_selector ----------------------------------------------------------


def test_call_tool_route_prefers_codex_then_claude() -> None:
    selection = select_provider_chain(
        route="call_tool",
        available_provider_ids={"openai-codex", "claude-cli"},
    )
    assert selection.primary == "openai-codex"
    assert selection.chain == ("openai-codex", "claude-cli")
    assert selection.ok


def test_direct_response_route_prefers_breadth_then_thinking() -> None:
    # Gemini ("breadth") absent -> falls to Claude ("thinking"), Codex last.
    selection = select_provider_chain(
        route="direct_response",
        available_provider_ids={"openai-codex", "claude-cli"},
    )
    assert selection.primary == "claude-cli"
    assert selection.chain == ("claude-cli", "openai-codex")
    assert "gemini" in selection.unavailable


def test_multi_step_route_chains_three_roles_when_available() -> None:
    selection = select_provider_chain(
        route="multi_step_agent_loop",
        available_provider_ids={"openai-codex", "claude-cli", "gemini"},
    )
    assert selection.chain == ("openai-codex", "claude-cli", "gemini")


def test_unknown_route_uses_default_role_order() -> None:
    selection = select_provider_chain(
        route="something_new",
        available_provider_ids={"openai-codex", "claude-cli"},
    )
    assert selection.primary == "openai-codex"
    assert selection.route == "something_new"


def test_no_available_providers_yields_no_primary() -> None:
    selection = select_provider_chain(route="call_tool", available_provider_ids=set())
    assert selection.primary is None
    assert selection.chain == ()
    assert not selection.ok


def test_custom_role_map_is_honored() -> None:
    role_map = ProviderRoleMap(heavy_lifting="codex-cli", thinking="claude-cli", breadth="gemini")
    selection = select_provider_chain(
        route="call_tool",
        available_provider_ids={"codex-cli", "claude-cli"},
        role_map=role_map,
    )
    assert selection.primary == "codex-cli"


def test_selection_emits_trace_event() -> None:
    events: list[tuple[str, dict]] = []
    select_provider_chain(
        route="call_tool",
        available_provider_ids={"openai-codex"},
        trace=lambda name, payload: events.append((name, payload or {})),
    )
    assert any(name == "multiagent_selection" for name, _ in events)


# -- fallback_executor ----------------------------------------------------------


@pytest.mark.asyncio
async def test_fallback_returns_first_success() -> None:
    async def run_one(provider_id: str) -> str:
        return f"answer from {provider_id}"

    outcome = await execute_with_fallback(chain=("openai-codex", "claude-cli"), run_one=run_one)
    assert outcome.ok
    assert outcome.provider_id == "openai-codex"
    assert outcome.value == "answer from openai-codex"
    assert not outcome.used_fallback


@pytest.mark.asyncio
async def test_fallback_advances_past_failing_provider() -> None:
    async def run_one(provider_id: str) -> str:
        if provider_id == "openai-codex":
            raise RuntimeError("codex exploded")
        return f"answer from {provider_id}"

    events: list[tuple[str, dict]] = []
    outcome = await execute_with_fallback(
        chain=("openai-codex", "claude-cli"),
        run_one=run_one,
        trace=lambda name, payload: events.append((name, payload or {})),
    )
    assert outcome.ok
    assert outcome.provider_id == "claude-cli"
    assert outcome.value == "answer from claude-cli"
    assert outcome.used_fallback
    # First attempt recorded as a failure with the error captured.
    assert outcome.attempts[0].provider_id == "openai-codex"
    assert outcome.attempts[0].ok is False
    assert "codex exploded" in (outcome.attempts[0].error or "")
    assert any(name == "multiagent_fallback" for name, _ in events)
    assert any(name == "multiagent_completed" for name, _ in events)


@pytest.mark.asyncio
async def test_fallback_exhausted_when_all_fail() -> None:
    async def run_one(provider_id: str) -> str:
        raise RuntimeError(f"{provider_id} down")

    outcome = await execute_with_fallback(chain=("openai-codex", "claude-cli"), run_one=run_one)
    assert not outcome.ok
    assert outcome.provider_id is None
    assert len(outcome.attempts) == 2
    assert all(not a.ok for a in outcome.attempts)


@pytest.mark.asyncio
async def test_should_retry_rejects_uncertain_result_and_falls_through() -> None:
    async def run_one(provider_id: str) -> dict:
        if provider_id == "claude-cli":
            return {"text": "I'm not sure", "uncertain": True}
        return {"text": "definitive answer from gemini", "uncertain": False}

    outcome = await execute_with_fallback(
        chain=("claude-cli", "gemini"),
        run_one=run_one,
        should_retry=lambda value: bool(value.get("uncertain")),
    )
    assert outcome.ok
    assert outcome.provider_id == "gemini"
    # Claude's uncertain result was rejected (soft failure).
    assert outcome.attempts[0].provider_id == "claude-cli"
    assert outcome.attempts[0].rejected is True


@pytest.mark.asyncio
async def test_fallback_times_out_and_advances() -> None:
    async def run_one(provider_id: str) -> str:
        if provider_id == "openai-codex":
            await asyncio.sleep(10)  # would block past the timeout
            return "never"
        return "fast answer"

    outcome = await execute_with_fallback(
        chain=("openai-codex", "claude-cli"),
        run_one=run_one,
        timeout_s=0.05,
    )
    assert outcome.ok
    assert outcome.provider_id == "claude-cli"
    assert "TimeoutError" in (outcome.attempts[0].error or "")


@pytest.mark.asyncio
async def test_empty_chain_is_a_clean_failure() -> None:
    async def run_one(provider_id: str) -> str:  # pragma: no cover - never called
        raise AssertionError("should not run")

    outcome = await execute_with_fallback(chain=(), run_one=run_one)
    assert not outcome.ok
    assert outcome.attempts == ()


# -- orchestrator_adapter -------------------------------------------------------


@pytest.mark.asyncio
async def test_orchestrator_runs_turn_through_selection() -> None:
    providers = {"openai-codex": object(), "claude-cli": object()}
    events: list[tuple[str, dict]] = []
    orch = MultiAgentOrchestrator(
        providers=providers,
        trace=lambda name, payload: events.append((name, payload or {})),
    )

    ran: list[str] = []

    async def run_on_provider(provider, provider_id: str) -> str:
        ran.append(provider_id)
        assert provider is providers[provider_id]
        return f"ok:{provider_id}"

    result = await orch.run_turn(route="call_tool", run_on_provider=run_on_provider)
    assert result.ok
    assert result.provider_id == "openai-codex"
    assert result.value == "ok:openai-codex"
    assert ran == ["openai-codex"]  # primary succeeded, no fallback needed
    assert result.selection.chain == ("openai-codex", "claude-cli")


@pytest.mark.asyncio
async def test_orchestrator_fallback_codex_fails_claude_succeeds() -> None:
    providers = {"openai-codex": object(), "claude-cli": object()}
    orch = MultiAgentOrchestrator(providers=providers)

    async def run_on_provider(provider, provider_id: str) -> str:
        if provider_id == "openai-codex":
            raise RuntimeError("codex timeout")
        return f"answer:{provider_id}"

    result = await orch.run_turn(route="call_tool", run_on_provider=run_on_provider)
    assert result.ok
    assert result.provider_id == "claude-cli"
    assert result.outcome.used_fallback


@pytest.mark.asyncio
async def test_orchestrator_reports_failure_when_no_providers() -> None:
    orch = MultiAgentOrchestrator(providers={})

    async def run_on_provider(provider, provider_id: str) -> str:  # pragma: no cover
        raise AssertionError("no provider should run")

    result = await orch.run_turn(route="call_tool", run_on_provider=run_on_provider)
    assert not result.ok
    assert result.provider_id is None


# -- sub-agent delegation -------------------------------------------------------


def test_subagent_task_requires_objective() -> None:
    with pytest.raises(ValueError, match="objective is required"):
        SubAgentTask(objective="   ")


def test_build_subagent_prompt_defines_bounded_handoff() -> None:
    task = SubAgentTask(
        objective="Inspect the session store API",
        context="Parent is wiring archive restore UX.",
        deliverables=("Relevant methods", "Known risks"),
        constraints=("Do not edit files",),
        max_response_chars=1200,
    )

    prompt = build_subagent_prompt(task)

    assert "bounded CopeNet sub-agent" in prompt
    assert "## Objective\nInspect the session store API" in prompt
    assert "## Context\nParent is wiring archive restore UX." in prompt
    assert "- Relevant methods" in prompt
    assert "- Do not edit files" in prompt
    assert "Keep the response under 1200 characters" in prompt


@pytest.mark.asyncio
async def test_delegate_subagent_task_runs_through_orchestrator_selection() -> None:
    providers = {"openai-codex": object(), "claude-cli": object()}
    orch = MultiAgentOrchestrator(providers=providers)
    task = SubAgentTask(objective="Summarize the TODO file", route="call_tool")
    calls: list[tuple[str, str]] = []

    async def run_subagent(provider, provider_id: str, prompt: str) -> str:
        assert provider is providers[provider_id]
        calls.append((provider_id, prompt))
        return "Summary: root TODO has backend/testing/frontend/product sections."

    result = await delegate_subagent_task(
        orchestrator=orch,
        task=task,
        run_subagent=run_subagent,
    )

    assert result.ok
    assert result.provider_id == "openai-codex"
    assert result.response == "Summary: root TODO has backend/testing/frontend/product sections."
    assert calls == [("openai-codex", result.prompt)]
    assert "Summarize the TODO file" in result.prompt


@pytest.mark.asyncio
async def test_delegate_subagent_task_falls_back_and_trims_response() -> None:
    providers = {"openai-codex": object(), "claude-cli": object()}
    orch = MultiAgentOrchestrator(providers=providers)
    task = SubAgentTask(objective="Investigate", route="call_tool", max_response_chars=220)

    async def run_subagent(provider, provider_id: str, prompt: str) -> str:
        if provider_id == "openai-codex":
            raise RuntimeError("primary unavailable")
        return "x" * 500

    result = await delegate_subagent_task(
        orchestrator=orch,
        task=task,
        run_subagent=run_subagent,
    )

    assert result.ok
    assert result.provider_id == "claude-cli"
    assert result.response is not None
    assert len(result.response) <= 220
    assert "truncated by CopeNet sub-agent boundary" in result.response
    assert result.turn.outcome.used_fallback
