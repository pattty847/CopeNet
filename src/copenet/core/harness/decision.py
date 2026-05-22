"""Trace-only HarnessDecision records for model-declared turn semantics."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Any, Callable, Literal, Protocol
from uuid import uuid4

from copenet.core.tools import ToolDescriptor


TraceRecorder = Callable[[str, dict[str, Any] | None], None]

HarnessDecisionStatus = Literal["parsed", "repaired", "fallback", "unavailable"]
HarnessControlMode = Literal["trace_only"]
RequestKind = Literal[
    "answer",
    "research",
    "create_artifact",
    "edit_artifact",
    "analyze_context",
    "code",
    "browser_action",
    "schedule",
    "conversation",
    "unsafe_or_disallowed",
]
Route = Literal[
    "direct_response",
    "ask_clarifying_question",
    "call_tool",
    "multi_step_agent_loop",
    "create_or_update_artifact",
    "refuse_or_redirect",
]
NextAction = Literal[
    "ANSWER",
    "ASK",
    "CALL_TOOL",
    "SEARCH_WEB",
    "SEARCH_FILES",
    "READ_CONTEXT",
    "RUN_CODE",
    "EDIT_ARTIFACT",
    "CREATE_TASK",
    "REFUSE",
    "STOP",
]
RiskLevel = Literal["low", "medium", "high"]
EvidenceRequirement = Literal[
    "none",
    "fresh_external_info",
    "direct_file_grounding",
    "read_before_edit",
    "verify_before_done",
    "artifact_created",
    "browser_observation",
    "explicit_user_confirmation",
]

REQUEST_KINDS = set(RequestKind.__args__)
ROUTES = set(Route.__args__)
NEXT_ACTIONS = set(NextAction.__args__)
RISK_LEVELS = set(RiskLevel.__args__)
EVIDENCE_REQUIREMENTS = set(EvidenceRequirement.__args__)


class HarnessDecisionValidationError(ValueError):
    """Raised when a model-authored HarnessDecision is not schema-valid."""


class HarnessDecisionProvider(Protocol):
    async def harness_decision(
        self,
        *,
        prompt: str,
        model: str | None,
        available_tools: list[dict[str, Any]],
        system_prompt: str | None = None,
    ) -> str:
        """Return one raw JSON HarnessDecision string."""


@dataclass(frozen=True)
class ToolDecision:
    """Trace-only model declaration about tool usefulness."""

    needed: bool
    candidate_tool_ids: list[str] = field(default_factory=list)
    selected_tool_id: str | None = None
    trace_note: str = ""

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "needed": self.needed,
            "candidate_tool_ids": list(self.candidate_tool_ids),
            "selected_tool_id": self.selected_tool_id,
            "trace_note": self.trace_note,
        }


@dataclass(frozen=True)
class HarnessDecision:
    """Model-authored trace-only routing declaration."""

    user_goal: str
    request_kind: RequestKind
    route: Route
    next_action: NextAction
    risk: RiskLevel
    evidence_requirements: list[EvidenceRequirement] = field(default_factory=list)
    tool_decision: ToolDecision = field(default_factory=lambda: ToolDecision(needed=False))
    missing: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    trace_note: str = ""

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "user_goal": self.user_goal,
            "request_kind": self.request_kind,
            "route": self.route,
            "next_action": self.next_action,
            "risk": self.risk,
            "evidence_requirements": list(self.evidence_requirements),
            "tool_decision": self.tool_decision.to_public_dict(),
            "missing": list(self.missing),
            "assumptions": list(self.assumptions),
            "trace_note": self.trace_note,
        }


@dataclass(frozen=True)
class HarnessDecisionRecord:
    """Persisted wrapper for one trace-only HarnessDecision attempt."""

    decision_id: str
    turn_id: str
    status: HarnessDecisionStatus
    decision: HarnessDecision | None
    control_mode: HarnessControlMode = "trace_only"
    schema_version: str = "harness_decision_record.v1"
    error_summary: str | None = None

    def to_public_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": self.schema_version,
            "decision_id": self.decision_id,
            "turn_id": self.turn_id,
            "control_mode": self.control_mode,
            "status": self.status,
            "decision": self.decision.to_public_dict() if self.decision is not None else None,
        }
        if self.error_summary:
            payload["error_summary"] = self.error_summary
        return payload


def new_turn_id() -> str:
    """Return a stable id for linking all events in one harness turn."""
    return f"turn-{uuid4().hex}"


def new_decision_id() -> str:
    """Return a stable id for linking one decision record to turn artifacts."""
    return f"decision-{uuid4().hex}"


def make_unavailable_decision_record(
    *,
    turn_id: str,
    decision_id: str,
    error_summary: str,
) -> HarnessDecisionRecord:
    return HarnessDecisionRecord(
        decision_id=decision_id,
        turn_id=turn_id,
        status="unavailable",
        decision=None,
        error_summary=error_summary,
    )


def make_fallback_decision_record(
    *,
    turn_id: str,
    decision_id: str,
    error_summary: str,
) -> HarnessDecisionRecord:
    return HarnessDecisionRecord(
        decision_id=decision_id,
        turn_id=turn_id,
        status="fallback",
        decision=None,
        error_summary=error_summary,
    )


def parse_harness_decision_record(
    raw: str,
    *,
    turn_id: str,
    decision_id: str,
    available_tool_ids: set[str],
) -> HarnessDecisionRecord:
    """Parse and validate a raw model-authored HarnessDecision JSON object."""
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HarnessDecisionValidationError(f"invalid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise HarnessDecisionValidationError("HarnessDecision must be a JSON object.")
    decision = _parse_harness_decision(value, available_tool_ids=available_tool_ids)
    return HarnessDecisionRecord(
        decision_id=decision_id,
        turn_id=turn_id,
        status="parsed",
        decision=decision,
    )


async def resolve_harness_decision_record(
    *,
    provider: object,
    prompt: str,
    model: str | None,
    system_prompt: str | None,
    tools: list[ToolDescriptor],
    turn_id: str,
    decision_id: str,
    trace: TraceRecorder | None = None,
) -> HarnessDecisionRecord:
    """Ask an optional provider hook for a decision without steering the main turn."""
    decision_hook = getattr(provider, "harness_decision", None)
    if not callable(decision_hook):
        record = make_unavailable_decision_record(
            turn_id=turn_id,
            decision_id=decision_id,
            error_summary="Provider has no harness_decision hook.",
        )
        _trace_decision(trace, record)
        return record
    try:
        raw = await decision_hook(
            prompt=prompt,
            model=model,
            available_tools=[tool.to_public_dict() for tool in tools],
            system_prompt=system_prompt,
        )
        if not isinstance(raw, str):
            raise HarnessDecisionValidationError("harness_decision hook returned non-text output.")
        record = parse_harness_decision_record(
            raw,
            turn_id=turn_id,
            decision_id=decision_id,
            available_tool_ids={tool.id for tool in tools},
        )
    except Exception as exc:
        record = make_fallback_decision_record(
            turn_id=turn_id,
            decision_id=decision_id,
            error_summary=str(exc),
        )
    _trace_decision(trace, record)
    return record


def _parse_harness_decision(value: dict[str, Any], *, available_tool_ids: set[str]) -> HarnessDecision:
    tool_decision = _parse_tool_decision(value.get("tool_decision"), available_tool_ids=available_tool_ids)
    return HarnessDecision(
        user_goal=_string(value.get("user_goal")),
        request_kind=_enum(value.get("request_kind"), REQUEST_KINDS, "request_kind"),  # type: ignore[arg-type]
        route=_enum(value.get("route"), ROUTES, "route"),  # type: ignore[arg-type]
        next_action=_enum(value.get("next_action"), NEXT_ACTIONS, "next_action"),  # type: ignore[arg-type]
        risk=_enum(value.get("risk"), RISK_LEVELS, "risk"),  # type: ignore[arg-type]
        evidence_requirements=[
            _enum(item, EVIDENCE_REQUIREMENTS, "evidence_requirements") for item in _string_list(value.get("evidence_requirements"))
        ],  # type: ignore[list-item]
        tool_decision=tool_decision,
        missing=_string_list(value.get("missing")),
        assumptions=_string_list(value.get("assumptions")),
        trace_note=_string(value.get("trace_note")),
    )


def _parse_tool_decision(value: Any, *, available_tool_ids: set[str]) -> ToolDecision:
    if value is None:
        return ToolDecision(needed=False)
    if not isinstance(value, dict):
        raise HarnessDecisionValidationError("tool_decision must be an object.")
    candidate_tool_ids = _string_list(value.get("candidate_tool_ids"))
    for tool_id in candidate_tool_ids:
        _validate_tool_id(tool_id, available_tool_ids)
    selected_tool_id = value.get("selected_tool_id")
    if selected_tool_id is not None:
        selected_tool_id = _string(selected_tool_id)
        _validate_tool_id(selected_tool_id, available_tool_ids)
    return ToolDecision(
        needed=bool(value.get("needed")),
        candidate_tool_ids=candidate_tool_ids,
        selected_tool_id=selected_tool_id,
        trace_note=_string(value.get("trace_note")),
    )


def _enum(value: Any, allowed: set[str], field_name: str) -> str:
    text = _string(value)
    if text not in allowed:
        raise HarnessDecisionValidationError(f"invalid {field_name}: {text}")
    return text


def _validate_tool_id(tool_id: str, available_tool_ids: set[str]) -> None:
    if tool_id not in available_tool_ids:
        raise HarnessDecisionValidationError(f"unknown tool id: {tool_id}")


def _string(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _trace_decision(trace: TraceRecorder | None, record: HarnessDecisionRecord) -> None:
    if trace is not None:
        trace("harness_decision_recorded", record.to_public_dict())
