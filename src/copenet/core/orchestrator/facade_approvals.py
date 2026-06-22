"""Approval and shell-permission facade methods."""

from __future__ import annotations

import asyncio


class ApprovalPermissionFacadeMixin:
    async def await_tool_approval(
        self,
        *,
        session_key: str,
        run_id: str,
        approval_id: str,
        request_payload: dict,
        emit_event,
        abort_event: "asyncio.Event",
        timeout_sec: float = 300.0,
    ) -> tuple[str, str | None]:
        """Park until the operator decides on a high-risk tool, or timeout/abort.

        Emits `approval.pending` with the ApprovalRequest, registers an event the
        decide RPC fires, and returns (decision, note). decision is one of
        'approved' | 'rejected' | 'timeout' | 'aborted'. The run stays alive
        (parked on this await) — no persist/reconstruct.
        """
        from copenet.core.sessions.transcript_store import utc_now_iso

        event = asyncio.Event()
        approval = {
            "approvalId": approval_id,
            "runId": run_id,
            "sessionKey": session_key,
            "status": "pending",
            "actionClass": "process_execution",
            "toolId": str(request_payload.get("toolId") or "shell.exec"),
            "proposedAction": {
                "description": str(request_payload.get("description") or ""),
                "target": request_payload.get("target"),
                "payload": request_payload.get("payload") or {},
            },
            "rationale": request_payload.get("rationale"),
            "createdAt": utc_now_iso(),
            "resolvedAt": None,
            "outcome": None,
        }
        # Keep the full approval payload so a reconnecting/reloaded client can
        # recover it via approvals.list — approval.pending is a one-shot push.
        self._pending_approvals[approval_id] = {"event": event, "decision": None, "note": None, "approval": approval}
        if emit_event is not None:
            await emit_event("approval.pending", {"approval": approval})

        decision = "timeout"
        note: str | None = None
        try:
            abort_wait = asyncio.create_task(abort_event.wait())
            decide_wait = asyncio.create_task(event.wait())
            done, pending = await asyncio.wait(
                {abort_wait, decide_wait}, timeout=timeout_sec, return_when=asyncio.FIRST_COMPLETED
            )
            for task in pending:
                task.cancel()
            if abort_wait in done and not event.is_set():
                decision = "aborted"
            elif event.is_set():
                entry = self._pending_approvals.get(approval_id) or {}
                decision = str(entry.get("decision") or "rejected")
                note = entry.get("note")
        finally:
            self._pending_approvals.pop(approval_id, None)

        if emit_event is not None:
            await emit_event(
                "approval.resolved",
                {"approvalId": approval_id, "runId": run_id, "sessionKey": session_key, "decision": decision},
            )
        return decision, note

    def list_pending_approvals(self) -> dict:
        """Return approvals still awaiting an operator decision.

        Bootstrap/reconnect recovery path: approval.pending is a one-shot push,
        so a client that reloads or connects mid-approval would otherwise never
        see the parked run. The run itself stays alive on its await; this just
        re-surfaces the card.
        """
        approvals = [
            entry["approval"]
            for entry in self._pending_approvals.values()
            if isinstance(entry, dict) and entry.get("approval")
        ]
        return {"approvals": approvals}

    def decide_approval(self, *, approval_id: str, decision: str, note: str | None = None) -> dict:
        """Record an operator's decision on a pending tool approval and wake the run."""
        entry = self._pending_approvals.get(approval_id.strip())
        if entry is None:
            return {"ok": False, "error": "no pending approval with that id"}
        normalized = decision.strip().lower()
        # "approved_always" approves this command AND persists it to the global
        # allowlist so it never asks again (Brick E). The gated executor handles
        # the persistence (it has the command + permission store on the context).
        if normalized not in {"approved", "rejected", "approved_always"}:
            return {"ok": False, "error": "decision must be 'approved', 'approved_always', or 'rejected'"}
        entry["decision"] = normalized
        entry["note"] = note
        event = entry.get("event")
        if isinstance(event, asyncio.Event):
            event.set()
        return {"ok": True, "approvalId": approval_id, "decision": normalized}

    def list_shell_allowlist(self) -> dict:
        """Return the operator's global shell allowlist entries."""
        return {"commands": self._permission_store.list_commands()}

    def add_shell_allowlist(self, command: str) -> dict:
        """Add a command to the global shell allowlist."""
        entry = self._permission_store.add(command)
        if entry is None:
            return {"ok": False, "error": "command is required"}
        return {"ok": True, "entry": entry, "commands": self._permission_store.list_commands()}

    def remove_shell_allowlist(self, command: str) -> dict:
        """Remove a command from the global shell allowlist."""
        removed = self._permission_store.remove(command)
        return {"ok": removed, "commands": self._permission_store.list_commands()}
