"""Central tool registry and execution entrypoint."""

from __future__ import annotations

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
            )
        if descriptor.category not in context.policy.allowed_categories:
            self._trace(
                context,
                "tool_blocked",
                {"toolId": descriptor.id, "reason": f"category not allowed: {descriptor.category}"},
            )
            return ToolExecutionResult(
                tool_id=descriptor.id,
                ok=False,
                summary=f"Tool blocked: {descriptor.id}",
                error=f"category not allowed: {descriptor.category}",
            )
        try:
            result = await self._builtin.run(request, context)
        except ToolBlockedError as exc:
            result = ToolExecutionResult(
                tool_id=descriptor.id,
                ok=False,
                summary=f"Tool blocked: {descriptor.id}",
                error=str(exc),
            )
            self._trace(
                context,
                "tool_blocked",
                {"toolId": descriptor.id, "reason": str(exc)},
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
