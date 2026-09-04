"""Exact-call operator approval and guarded execution."""
from copy import deepcopy
from uuid import uuid4
from copenet.core.tools import ToolExecutionResult

def make_approval_gated_executor(base_executor, *, orchestrator, emit_event, session_key, run_id, abort_event):
    """Wrap a tool executor so a high-risk result pauses for operator approval.

    When a tool returns policyDecision == "approval_required", the run parks
    (await_tool_approval) until the operator decides via the decide RPC. On
    approve the exact command is re-run with the gate bypassed; on reject or
    timeout the blocked result is returned so the model adapts. With no
    emit_event side channel (e.g. CLI) there's no operator to ask, so the
    blocked result is returned as before.
    """

    async def execute(request, context):
        result = await base_executor(request, context)
        output = result.output if isinstance(result.output, dict) else {}
        if result.ok or output.get("policyDecision") != "approval_required" or emit_event is None:
            return result

        approval_id = f"appr-{uuid4().hex[:12]}"
        command = str(output.get("command") or "") if request.tool_id == "shell.exec" else ""
        target = command or str(output.get("target") or request.arguments.get("documentId") or request.tool_id)
        decision, note = await orchestrator.await_tool_approval(
            session_key=session_key,
            run_id=run_id,
            approval_id=approval_id,
            request_payload={
                "toolId": result.tool_id,
                "actionClass": "chart_annotation" if request.tool_id in {"market.chart.apply", "market.chart.undo"} else "process_execution",
                "description": f"Run shell command: {command}" if command else f"Run {result.tool_id}",
                "target": target,
                "payload": deepcopy(request.arguments),
                "rationale": output.get("policySummary"),
            },
            emit_event=emit_event,
            abort_event=abort_event,
        )
        if abort_event.is_set():
            decision = "aborted"
        if decision in ("approved", "approved_always"):
            # Re-run the exact call with the gate bypassed. The shell pattern gate
            # checks `approved_commands` by command string; the Barricade side-
            # effect gate checks `barricade_approved` by an argument-DIGEST key, so
            # approving one write doesn't bless a different write to the same path.
            from copenet.core.tools.barricade import approval_key

            command_key = command or str(output.get("target") or result.tool_id)
            # "Always allow" → persist to the global shell allowlist (Brick E) so
            # this exact command runs without asking on future runs. Scoped to
            # shell.exec specifically: `command` falls back to `output["target"]`
            # for non-shell tools (barricade._side_effect_gate sets "command" only
            # for shell.exec), and a target like a file path must never be written
            # into the shell allowlist — that would grant standing, cross-session,
            # cross-Access-mode shell authority from approving an unrelated write.
            # Best-effort: a store failure must not break the in-flight approve.
            if (
                decision == "approved_always"
                and result.tool_id == "shell.exec"
                and command
                and getattr(context, "permission_store", None) is not None
            ):
                try:
                    context.permission_store.add(command)
                except Exception:  # noqa: BLE001 - persistence is best-effort here
                    pass
            if request.tool_id == "shell.exec":
                context.ephemeral.setdefault("approved_commands", set()).add(command_key)
            barricade_approved = context.ephemeral.setdefault("barricade_approved", set())
            (barricade_approved if isinstance(barricade_approved, set) else set()).add(approval_key(request))
            if not isinstance(barricade_approved, set):
                context.ephemeral["barricade_approved"] = {approval_key(request)}
            return await base_executor(request, context)
        # Rejected / timed out / aborted. Without this the model gets back the
        # original approval_required payload — indistinguishable from the pending
        # state — and plausibly re-issues the same command, re-paging the operator.
        # Tell it a human decided, so it adapts instead of retrying.
        rejected_output = {
            **output,
            "policyDecision": "rejected_by_operator",
            "operatorDecision": decision,
            "operatorNote": note,
            "policySummary": (
                f"The operator {decision} this action. Do not retry it; "
                "choose a different approach or ask the user."
            ),
        }
        return ToolExecutionResult(
            tool_id=result.tool_id,
            ok=False,
            summary=f"Operator {decision} the action.",
            error=f"operator {decision} the action",
            output=rejected_output,
        )

    return execute
