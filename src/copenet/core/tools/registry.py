"""Central tool registry and execution entrypoint."""

from __future__ import annotations

import json
from typing import Any

from .barricade import post_dispatch_record, pre_dispatch_gate
from .builtin_readonly import MANIFEST_TOOL_IDS, BuiltinReadonlyTools
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
        """Return the model-facing tool manifest (Phase 3: the five primitives).

        Every handler stays registered for execution/policy routing (see
        get_descriptor / execute), but only the manifest subset is offered to the
        model and exposed over the tools.list RPC.
        """
        return [
            self._descriptors[key]
            for key in sorted(self._descriptors)
            if key in MANIFEST_TOOL_IDS
        ]

    def list_registered_tools(self) -> list[ToolDescriptor]:
        """Return every registered tool descriptor (including non-manifest handlers)."""
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
        # CopeNet Barricade (COPENET_BARRICADE=1): contract privilege when the
        # run has ingested untrusted content, and guard web.fetch egress. Runs
        # BEFORE the handler so a gated side effect never actually happens.
        barricade_block = pre_dispatch_gate(request, context, descriptor)
        if barricade_block is not None:
            self._trace(
                context,
                "tool_blocked",
                {
                    "toolId": descriptor.id,
                    "reason": barricade_block.error,
                    "policyDecision": barricade_block.output.get("policyDecision"),
                    "policySummary": barricade_block.output.get("policySummary"),
                },
            )
            return barricade_block

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
                # Put the error in output too: the native/Responses loops feed the
                # model only result.output, so without this a frontier model that
                # passes a bad argument sees literally "{}" and has to guess.
                output={"error": str(exc), "policyDecision": "tool_error"},
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
        # Barricade: account for taint + sensitive reads from this result so the
        # NEXT side-effect call in this run is gated appropriately.
        post_dispatch_record(request, context, result)
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
