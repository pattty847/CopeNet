"""Central tool registry and execution entrypoint."""

from __future__ import annotations

import json
from typing import Any

from .builtin_readonly import BuiltinReadonlyTools
from .contracts import ToolBlockedError, ToolDescriptor, ToolExecutionContext, ToolExecutionRequest, ToolExecutionResult
from .policy import ToolPolicy


class ToolRegistry:
    """Central v1 tool registry and safe execution runtime."""

    def __init__(self, policy: ToolPolicy | None = None) -> None:
        self._policy = policy or ToolPolicy()
        self._descriptors: dict[str, ToolDescriptor] = {}
        self._builtin = BuiltinReadonlyTools()
        for descriptor in self._builtin.descriptors():
            self._descriptors[descriptor.id] = descriptor

    @property
    def policy(self) -> ToolPolicy:
        """Return the active tool policy."""
        return self._policy

    def list_tools(self) -> list[ToolDescriptor]:
        """Return all registered tools."""
        return [self._descriptors[key] for key in sorted(self._descriptors)]

    def list_public_tools(self) -> list[dict[str, Any]]:
        """Return public tool descriptors for RPC clients."""
        return [descriptor.to_public_dict() for descriptor in self.list_tools()]

    def get_descriptor(self, tool_id: str) -> ToolDescriptor | None:
        """Return one registered tool descriptor by id."""
        return self._descriptors.get(tool_id)

    async def execute(
        self,
        request: ToolExecutionRequest,
        context: ToolExecutionContext,
    ) -> ToolExecutionResult:
        """Execute one tool request under the current policy."""
        descriptor = self._descriptors.get(request.tool_id)
        if descriptor is None:
            self._trace(context, "tool_blocked", {"toolId": request.tool_id, "reason": "unknown tool"})
            return ToolExecutionResult(
                tool_id=request.tool_id,
                ok=False,
                summary=f"Unknown tool: {request.tool_id}",
                error="unknown tool",
                output={
                    "workspaceRoot": str(context.session_workspace_root),
                    "accessAction": "unknown",
                    "policyDecision": "unsafe_unknown",
                    "policySummary": "Unknown tools are blocked.",
                },
            )
        if descriptor.category not in context.policy.allowed_categories:
            if descriptor.category == "repo-write":
                error = "write tool unavailable in current mode"
                policy_decision = "write_blocked"
                policy_summary = "Current tool mode does not allow repository write tools."
            elif descriptor.category == "artifact":
                error = "artifact tool unavailable in current mode"
                policy_decision = "unsafe_unknown"
                policy_summary = "Current tool mode does not allow artifact creation."
            else:
                error = f"category not allowed: {descriptor.category}"
                policy_decision = "unsafe_unknown"
                policy_summary = f"Tool category {descriptor.category} is blocked by policy."
            self._trace(
                context,
                "tool_blocked",
                {"toolId": descriptor.id, "reason": error},
            )
            return ToolExecutionResult(
                tool_id=descriptor.id,
                ok=False,
                summary=f"Tool unavailable in current mode: {descriptor.id}",
                error=error,
                output={
                    "workspaceRoot": str(context.session_workspace_root),
                    "accessAction": "write" if descriptor.category in {"repo-write", "artifact"} else "unknown",
                    "policyDecision": policy_decision,
                    "policySummary": policy_summary,
                },
            )
        _track_tool_repetition(context, request=request)
        try:
            result = await self._builtin.run(request, context)
        except ToolBlockedError as exc:
            result = ToolExecutionResult(
                tool_id=descriptor.id,
                ok=False,
                summary=f"Tool blocked: {descriptor.id}",
                error=str(exc),
                output={
                    "target": exc.target,
                    "workspaceRoot": exc.workspace_root or str(context.session_workspace_root),
                    "scope": exc.scope,
                    "accessAction": exc.access_action,
                    "policyDecision": exc.policy_decision,
                    "policySummary": exc.policy_summary,
                },
            )
            self._trace(
                context,
                "tool_blocked",
                {
                    "toolId": descriptor.id,
                    "reason": str(exc),
                    "target": exc.target,
                    "workspaceRoot": exc.workspace_root or str(context.session_workspace_root),
                    "scope": exc.scope,
                    "accessAction": exc.access_action,
                    "policyDecision": exc.policy_decision,
                    "policySummary": exc.policy_summary,
                },
            )
            return result
        except Exception as exc:
            result = ToolExecutionResult(
                tool_id=descriptor.id,
                ok=False,
                summary=f"Tool failed: {descriptor.id}",
                error=str(exc),
            )
        self._trace(
            context,
            "tool_executed",
            {
                "toolId": descriptor.id,
                "ok": result.ok,
                "summary": result.summary,
                "error": result.error,
            },
        )
        return result

    @staticmethod
    def _trace(
        context: ToolExecutionContext,
        event: str,
        payload: dict[str, Any],
    ) -> None:
        if context.trace is not None:
            context.trace(event, payload)


def _track_tool_repetition(
    context: ToolExecutionContext,
    *,
    request: ToolExecutionRequest,
) -> None:
    state = context.ephemeral.setdefault("tool_repetition_state", {})
    signature = json.dumps(
        {
            "toolId": request.tool_id,
            "arguments": request.arguments,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    last_signature = state.get("last_signature")
    if last_signature == signature:
        count = int(state.get("count") or 0) + 1
    else:
        count = 1
    state["last_signature"] = signature
    state["count"] = count
    state["current"] = {
        "toolId": request.tool_id,
        "signature": signature,
        "count": count,
    }
