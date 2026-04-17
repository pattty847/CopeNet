"""Turn-scoped runtime state for CopeNet tool continuation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


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
        }


@dataclass(frozen=True)
class ForkSnapshot:
    """Minimal branch snapshot shape reserved for future branching work."""

    kind: str
    index: int | None = None

