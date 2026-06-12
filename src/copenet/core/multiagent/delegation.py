"""Bounded sub-agent delegation primitives for CopeNet.

This module is intentionally small and runtime-agnostic: it builds the prompt
packet for a delegated investigation and runs it through the existing
MultiAgentOrchestrator provider-selection/fallback path. The live chat runtime
can wire this in later without changing the product contract.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Mapping, Sequence

from .orchestrator_adapter import MultiAgentOrchestrator, MultiAgentTurnResult


SubAgentRunner = Callable[[Any, str, str], Awaitable[str]]


@dataclass(frozen=True)
class SubAgentTask:
    """A bounded task handed to a sub-agent.

    The parent agent should provide enough context for the sub-agent to work
    independently, plus explicit deliverables so the result can be compactly
    merged back into the parent turn.
    """

    objective: str
    context: str = ""
    deliverables: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()
    route: str = "direct_response"
    max_response_chars: int = 6000
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        objective = self.objective.strip()
        if not objective:
            raise ValueError("SubAgentTask objective is required")
        if self.max_response_chars < 200:
            raise ValueError("SubAgentTask max_response_chars must be at least 200")
        object.__setattr__(self, "objective", objective)
        object.__setattr__(self, "context", self.context.strip())
        object.__setattr__(self, "deliverables", _clean_items(self.deliverables))
        object.__setattr__(self, "constraints", _clean_items(self.constraints))


@dataclass(frozen=True)
class SubAgentResult:
    """Result packet returned to the parent agent after delegation."""

    task: SubAgentTask
    prompt: str
    turn: MultiAgentTurnResult
    response: str | None

    @property
    def ok(self) -> bool:
        return self.turn.ok and self.response is not None

    @property
    def provider_id(self) -> str | None:
        return self.turn.provider_id


def build_subagent_prompt(task: SubAgentTask) -> str:
    """Build the isolated prompt sent to a delegated sub-agent."""
    sections = [
        "You are a bounded CopeNet sub-agent working on one delegated task.",
        "Stay within the task. Do not ask the parent for live clarification unless the task is impossible.",
        "Return only a concise handoff for the parent agent: findings, evidence, and recommended next action.",
        "",
        "## Objective",
        task.objective,
    ]
    if task.context:
        sections.extend(["", "## Context", task.context])
    if task.deliverables:
        sections.extend(["", "## Deliverables", _format_bullets(task.deliverables)])
    if task.constraints:
        sections.extend(["", "## Constraints", _format_bullets(task.constraints)])
    sections.extend(
        [
            "",
            "## Response format",
            "- Summary: 1-3 sentences",
            "- Findings: bullet list with concrete evidence",
            "- Risks / unknowns: bullet list, or 'none'",
            "- Recommended next action: one bullet",
            "",
            f"Keep the response under {task.max_response_chars} characters.",
        ]
    )
    return "\n".join(sections)


async def delegate_subagent_task(
    *,
    orchestrator: MultiAgentOrchestrator,
    task: SubAgentTask,
    run_subagent: SubAgentRunner,
    timeout_s: float | None = None,
) -> SubAgentResult:
    """Run one bounded delegated task through provider selection + fallback.

    `run_subagent(provider, provider_id, prompt)` is supplied by the caller so
    this primitive can be tested without importing the live chat runtime.
    """
    prompt = build_subagent_prompt(task)

    async def run_on_provider(provider: Any, provider_id: str) -> str:
        response = await run_subagent(provider, provider_id, prompt)
        return _trim_response(response, task.max_response_chars)

    turn = await orchestrator.run_turn(
        route=task.route,
        run_on_provider=run_on_provider,
        timeout_s=timeout_s,
    )
    response = turn.value if turn.ok and isinstance(turn.value, str) else None
    return SubAgentResult(task=task, prompt=prompt, turn=turn, response=response)


def _clean_items(items: Sequence[str]) -> tuple[str, ...]:
    return tuple(item.strip() for item in items if item.strip())


def _format_bullets(items: Sequence[str]) -> str:
    return "\n".join(f"- {item}" for item in items)


def _trim_response(response: str, max_chars: int) -> str:
    if len(response) <= max_chars:
        return response
    marker = "\n\n[truncated by CopeNet sub-agent boundary]"
    return response[: max_chars - len(marker)].rstrip() + marker
