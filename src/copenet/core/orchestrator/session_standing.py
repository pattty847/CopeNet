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
    SharedWork,
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
    last_runs: dict[str, object] = {}

    for entry in entries:
        key = entry.session_key
        ledgers[key] = summarize_ledger(orchestrator._change_ledger_store.entries(key))
        last_runs[key] = _last_run(orchestrator, key)
        workspace = _workspace_for(orchestrator, entry, last_runs[key])
        # "" means we cannot say where this session's work went, so it shares a branch
        # with nobody and gets no branch state.
        workspaces[key] = str(workspace) if workspace is not None else ""
        if workspace is not None and str(workspace) not in branches:
            branches[str(workspace)] = read_branch_state(workspace)

    shared = find_shared_paths(ledgers, workspaces)

    rows: list[dict] = []
    for entry in entries:
        key = entry.session_key
        state_record = orchestrator._session_state_store.get(key)
        last_run = last_runs[key]
        approval_command = approval_command_from(last_run)
        ledger = ledgers[key]
        branch = branches.get(workspaces[key], BranchState())
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


def _workspace_for(orchestrator: "Orchestrator", entry, last_run=None) -> Path | None:
    """Where this session's work actually went, or None when we cannot say.

    The run record stamps the workspace it used, and that is the authoritative
    answer — falling back to the host's current workdir credited every old session
    (benchmark runs against long-gone fixture repos included) with whatever branch
    this checkout happens to be on. A session whose workspace no longer exists gets
    no branch state rather than a borrowed one.
    """
    recorded = ""
    if last_run is not None:
        metadata = getattr(last_run, "metadata", None)
        if isinstance(metadata, dict):
            recorded = str(metadata.get("workspaceRoot") or "").strip()
    candidate = recorded or (entry.workspace_root or "").strip()
    if not candidate:
        # Never ran, so nothing has been written anywhere yet.
        return None
    path = Path(candidate)
    return path if path.is_dir() else None


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


def shared_work_for(
    orchestrator: "Orchestrator", *, session_key: str, workspace_root: Path
) -> list[SharedWork]:
    """Other open sessions with uncommitted work in this workspace, newest first.

    Only non-archived sessions that actually changed something, and never the caller.
    The agent has no way to see another session, so this is the only way it learns it
    is about to edit a branch another thread is already using.
    """
    own_paths = summarize_ledger(orchestrator._change_ledger_store.entries(session_key)).paths
    rows: list[SharedWork] = []
    for entry in orchestrator._session_store.list_sessions(include_archived=False):
        if entry.session_key == session_key:
            continue
        other = _workspace_for(orchestrator, entry, _last_run(orchestrator, entry.session_key))
        if other is None or str(other) != str(workspace_root):
            continue
        ledger = summarize_ledger(orchestrator._change_ledger_store.entries(entry.session_key))
        if ledger.file_count == 0:
            continue
        rows.append(
            SharedWork(
                session_key=entry.session_key,
                title=(entry.title or entry.session_key).strip(),
                files=list(ledger.recent_files),
                overlapping=sorted(Path(path).name for path in (ledger.paths & own_paths)),
            )
        )
    # A thread that overlaps is the one that will actually collide; put it first.
    rows.sort(key=lambda work: (not work.overlapping, work.session_key))
    return rows
