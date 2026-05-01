"""Turn-scoped runtime state for CopeNet tool continuation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from copenet.core.tools import ToolExecutionResult


TransitionReason = str
TerminalReason = str


@dataclass
class TurnState:
    """Mutable runtime state for one in-flight turn."""

    pending_input: list[dict[str, Any]] = field(default_factory=list)
    transition_reason: TransitionReason = "start_turn"
    pending_approvals: dict[str, Any] = field(default_factory=dict)
    granted_permissions: dict[str, Any] = field(default_factory=dict)
    tool_call_count: int = 0
    token_usage_at_turn_start: dict[str, Any] | None = None
    terminal_reason: TerminalReason | None = None
    visited_tools: list[str] = field(default_factory=list)
    visited_paths: list[str] = field(default_factory=list)
    grounding_actions: list[str] = field(default_factory=list)
    evidence_items: list[dict[str, Any]] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    failed_actions: list[dict[str, Any]] = field(default_factory=list)
    final_rejection_count: int = 0
    last_tool_result_summary: str = ""
    last_final_gate_reason_code: str | None = None


    def record_tool_step(self, *, tool_id: str, arguments: dict[str, Any], result: ToolExecutionResult) -> None:
        """Record compact controller evidence from one tool result."""
        self.visited_tools.append(tool_id)
        self.last_tool_result_summary = result.summary
        body = result.body if result.body is not None else result.output
        paths: list[str] = []
        if isinstance(arguments.get("path"), str) and arguments.get("path"):
            paths.append(str(arguments["path"]))
        if isinstance(body, dict):
            direct_path = body.get("path")
            if isinstance(direct_path, str) and direct_path:
                paths.append(direct_path)
            for item in body.get("entries") or []:
                if isinstance(item, dict) and isinstance(item.get("path"), str):
                    paths.append(str(item["path"]))
            for item in body.get("matches") or []:
                if isinstance(item, dict) and isinstance(item.get("path"), str):
                    paths.append(str(item["path"]))
        for path in paths:
            if path and path not in self.visited_paths:
                self.visited_paths.append(path)

        category = _classify_evidence_category(tool_id)
        if category == "grounding" and tool_id not in self.grounding_actions:
            self.grounding_actions.append(tool_id)
        evidence_item = {
            "toolId": tool_id,
            "category": category,
            "summary": result.summary,
            "pathHints": paths[:8],
            "ok": result.ok,
        }
        self.evidence_items.append(evidence_item)
        if not result.ok:
            self.failed_actions.append({
                "toolId": tool_id,
                "summary": result.summary,
                "error": result.error,
            })

    def register_final_rejection(self, *, reason_code: str | None, missing_requirements: list[str]) -> None:
        self.final_rejection_count += 1
        self.last_final_gate_reason_code = reason_code
        self.transition_reason = "final_gate_rejected"
        self.open_questions = list(missing_requirements)

    @property
    def evidence_ledger(self) -> dict[str, Any]:
        return {
            "visitedTools": list(self.visited_tools),
            "visitedPaths": list(self.visited_paths),
            "groundingActions": list(self.grounding_actions),
            "evidenceItems": [dict(item) for item in self.evidence_items],
            "openQuestions": list(self.open_questions),
            "failedActions": [dict(item) for item in self.failed_actions],
            "lastToolResultSummary": self.last_tool_result_summary,
        }

    def queue_input(self, item: dict[str, Any], *, reason: TransitionReason) -> None:
        """Append one normalized input item and update the transition reason."""
        self.pending_input.append(dict(item))
        self.transition_reason = reason

    def drain_pending_input(self) -> list[dict[str, Any]]:
        """Drain queued normalized inputs for the next loop pass."""
        rows = [dict(item) for item in self.pending_input]
        self.pending_input.clear()
        return rows

    def has_pending_input(self) -> bool:
        """Return whether the turn still has queued follow-up input."""
        return bool(self.pending_input)

    def to_public_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly snapshot for tracing and run records."""
        return {
            "pendingInputCount": len(self.pending_input),
            "transitionReason": self.transition_reason,
            "pendingApprovalCount": len(self.pending_approvals),
            "grantedPermissions": dict(self.granted_permissions),
            "toolCallCount": self.tool_call_count,
            "tokenUsageAtTurnStart": dict(self.token_usage_at_turn_start or {}),
            "terminalReason": self.terminal_reason,
            "visitedTools": list(self.visited_tools),
            "visitedPaths": list(self.visited_paths),
            "groundingActions": list(self.grounding_actions),
            "evidenceItems": [dict(item) for item in self.evidence_items],
            "openQuestions": list(self.open_questions),
            "failedActions": [dict(item) for item in self.failed_actions],
            "finalRejectionCount": self.final_rejection_count,
            "lastToolResultSummary": self.last_tool_result_summary,
            "lastFinalGateReasonCode": self.last_final_gate_reason_code,
            "evidenceLedger": self.evidence_ledger,
        }


@dataclass(frozen=True)
class ForkSnapshot:
    """Minimal branch snapshot shape reserved for future branching work."""

    kind: str
    index: int | None = None


def _classify_evidence_category(tool_id: str) -> str:
    if tool_id == "files.list":
        return "reconnaissance"
    if tool_id in {"files.search", "files.rg"}:
        return "directional"
    if tool_id == "files.read":
        return "grounding"
    if tool_id == "context.prepare":
        return "contextual"
    if tool_id == "patch.apply":
        return "mutation"
    if tool_id == "test.run":
        return "verification"
    return "tool"
