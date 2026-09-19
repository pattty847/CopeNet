"""Build the session list's standing rows from the stores that already hold the facts.

One call answers the whole sidebar: the change ledger per session, the last run's tool
counts and failed verification, one git read per distinct workspace (not per session),
and the cross-session file overlap that catches a branch holding two features.

See core/sessions/session_standing.py for what each fact means and why.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from copenet.core.sessions.session_standing import (
    BranchState,
    LedgerSummary,
    SessionStanding,
    approval_command_from,
    find_shared_paths,
    read_branch_state,
    resolve_state,
    summarize_ledger,
)

if TYPE_CHECKING:
    from . import Orchestrator


def list_session_standing(
    orchestrator: "Orchestrator", *, include_archived: bool = False
) -> list[dict]:
    """Return one standing row per session, newest activity first."""
    entries = orchestrator._session_store.list_sessions(include_archived=include_archived)
    ledgers: dict[str, LedgerSummary] = {}
    workspaces: dict[str, str] = {}
    branches: dict[str, BranchState] = {}

    for entry in entries:
        key = entry.session_key
        ledgers[key] = summarize_ledger(orchestrator._change_ledger_store.entries(key))
        workspace = _workspace_for(orchestrator, entry)
        workspaces[key] = str(workspace)
        if str(workspace) not in branches:
            branches[str(workspace)] = read_branch_state(workspace)

    shared = find_shared_paths(ledgers, workspaces)

    rows: list[dict] = []
    for entry in entries:
        key = entry.session_key
        state_record = orchestrator._session_state_store.get(key)
        last_run = _last_run(orchestrator, key)
        approval_command = approval_command_from(last_run)
        ledger = ledgers[key]
        branch = branches[workspaces[key]]
        standing_note = getattr(state_record, "standing_note", None) if state_record else None
        standing_done = bool(getattr(state_record, "standing_done", False)) if state_record else False
        rows.append(
            SessionStanding(
                session_key=key,
                state=resolve_state(
                    in_flight=bool(entry.in_flight_run_id),
                    approval_command=approval_command,
                    ledger=ledger,
                    branch=branch,
                    standing_done=standing_done,
                ),
                standing_note=standing_note,
                standing_done=standing_done,
                ledger=ledger,
                branch=branch,
                tool_calls=_tool_calls(last_run),
                verification_failed=_verification_failed(last_run),
                approval_command=approval_command,
                shares_with=shared.get(key, []),
            ).to_public_dict()
        )
    return rows


def _workspace_for(orchestrator: "Orchestrator", entry) -> Path:
    """Resolve one session's workspace the same way a run does."""
    if not entry.workspace_root:
        return orchestrator._workdir
    try:
        return Path(orchestrator.validate_workspace_root(entry.workspace_root))
    except (ValueError, OSError):
        return orchestrator._workdir


def _last_run(orchestrator: "Orchestrator", session_key: str):
    runs = orchestrator._run_store.list_for_session(session_key, limit=1)
    return runs[-1] if runs else None


def _tool_calls(run) -> int:
    if run is None:
        return 0
    metrics = getattr(run, "coding_metrics", None)
    if isinstance(metrics, dict):
        return int(metrics.get("toolCalls") or 0)
    return len(getattr(run, "tool_steps", []) or [])


def _verification_failed(run) -> bool:
    """Did the run stop with the suite red? An exit code, not an interpretation."""
    if run is None:
        return False
    metrics = getattr(run, "coding_metrics", None)
    if not isinstance(metrics, dict):
        return False
    verification = metrics.get("verification")
    return bool(isinstance(verification, dict) and verification.get("lastFailed"))
