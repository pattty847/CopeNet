"""Where every session stands: the facts behind one row of the session list.

The old row showed a title generated once from the first exchange plus the provider
and model, which are the same on nearly every row. This module answers the questions
an operator actually opens the list with — is anything running, did a model finish and
commit while I was elsewhere, which thread left the suite red, and are two threads
quietly editing the same file on one branch.

Everything here is DERIVED. The change ledger has the files and the line counts, the
run record has the tool counts and the failed verification, git has the branch. The
one thing no fact answers — where the work stands — is the model's own line, written
through the session.standing tool and carried on SessionStateRecord.

The frontend composes the sentence; this emits the facts (runtime/sessionStanding.ts).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import subprocess
from typing import Any

# Enough recent files to recognise a thread by; the row shows two or three and a count.
LEDGER_FILE_LIMIT = 6
# One git call per distinct workspace, not per session, and never a slow one.
GIT_TIMEOUT_SEC = 4.0
TRUNK_CANDIDATES = ("main", "master")


@dataclass(frozen=True)
class LedgerSummary:
    """What one session changed, folded from its change ledger."""

    lines_added: int = 0
    lines_removed: int = 0
    file_count: int = 0
    recent_files: list[str] = field(default_factory=list)
    paths: frozenset[str] = frozenset()
    area: str | None = None

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "linesAdded": self.lines_added,
            "linesRemoved": self.lines_removed,
            "fileCount": self.file_count,
            "recentFiles": list(self.recent_files),
            "area": self.area,
        }


@dataclass(frozen=True)
class BranchState:
    """One workspace's branch, shared by every session pointed at it."""

    branch: str | None = None
    commits_ahead: int = 0
    trunk: str | None = None

    def to_public_dict(self) -> dict[str, Any]:
        return {"branch": self.branch, "commitsAhead": self.commits_ahead, "trunk": self.trunk}


@dataclass(frozen=True)
class SessionStanding:
    """One row of the session list."""

    session_key: str
    state: str
    standing_note: str | None
    standing_done: bool
    ledger: LedgerSummary
    branch: BranchState
    tool_calls: int
    verification_failed: bool
    approval_command: str | None
    shares_with: list[dict[str, str]]

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "sessionKey": self.session_key,
            "state": self.state,
            "standingNote": self.standing_note,
            "standingDone": self.standing_done,
            "ledger": self.ledger.to_public_dict(),
            "branch": self.branch.to_public_dict(),
            "toolCalls": self.tool_calls,
            "verificationFailed": self.verification_failed,
            "approvalCommand": self.approval_command,
            "sharesWith": [dict(row) for row in self.shares_with],
        }


def summarize_ledger(entries: list[Any]) -> LedgerSummary:
    """Fold one session's ledger entries into the row's third line."""
    if not entries:
        return LedgerSummary()
    added = sum(int(entry.lines_added or 0) for entry in entries)
    removed = sum(int(entry.lines_removed or 0) for entry in entries)
    # Newest touch first, one slot per path, so the row names what was worked on last.
    ordered: list[str] = []
    for entry in reversed(entries):
        if entry.path and entry.path not in ordered:
            ordered.append(entry.path)
    return LedgerSummary(
        lines_added=added,
        lines_removed=removed,
        file_count=len(ordered),
        recent_files=[Path(path).name for path in ordered[:LEDGER_FILE_LIMIT]],
        paths=frozenset(ordered),
        area=common_area(ordered),
    )


def common_area(paths: list[str]) -> str | None:
    """The directory a thread's work lives in, used to group the list by place.

    Two segments where a path has them ("core/market"), the first otherwise. Threads
    that touched several areas group under the one they touched most recently, which
    is the one the operator was last thinking about.
    """
    for path in paths:
        parts = [part for part in Path(path).parts if part not in (".", "/")][:-1]
        if not parts:
            continue
        return "/".join(parts[:2]) if len(parts) >= 2 else parts[0]
    return None


def read_branch_state(workspace_root: Path) -> BranchState:
    """Read one workspace's branch and how far it is ahead of its trunk."""
    branch = _git(workspace_root, ["rev-parse", "--abbrev-ref", "HEAD"])
    if not branch or branch == "HEAD":
        return BranchState()
    trunk = next(
        (name for name in TRUNK_CANDIDATES if _git(workspace_root, ["rev-parse", "--verify", "--quiet", name])),
        None,
    )
    if trunk is None or branch == trunk:
        return BranchState(branch=branch, commits_ahead=0, trunk=trunk)
    ahead = _git(workspace_root, ["rev-list", "--count", f"{trunk}..HEAD"])
    try:
        count = int(ahead or "0")
    except ValueError:
        count = 0
    return BranchState(branch=branch, commits_ahead=count, trunk=trunk)


def _git(workspace_root: Path, args: list[str]) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=str(workspace_root),
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_SEC,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def approval_command_from(run: Any | None) -> str | None:
    """The command a run stopped on, when policy asked for the operator's word."""
    if run is None:
        return None
    for step in reversed(list(getattr(run, "tool_steps", []) or [])):
        if not isinstance(step, dict):
            continue
        effect = step.get("effect") if isinstance(step.get("effect"), dict) else {}
        decision = step.get("policyDecision") or effect.get("policyDecision")
        if decision != "approval_required":
            continue
        arguments = step.get("arguments") if isinstance(step.get("arguments"), dict) else {}
        command = str(arguments.get("command") or "").strip()
        return command[:120] if command else str(step.get("toolId") or "a guarded tool")
    return None


def resolve_state(
    *,
    in_flight: bool,
    approval_command: str | None,
    ledger: LedgerSummary,
    branch: BranchState,
    standing_done: bool,
) -> str:
    """One exclusive state per thread, most urgent first.

    "waiting on you" is deliberately absent: every reply ends with the model waiting,
    so the state carried no information. What varies is the state of the WORK.
    """
    if in_flight:
        return "running"
    if approval_command:
        return "blocked"
    if ledger.file_count == 0:
        return "talk"
    if branch.commits_ahead > 0:
        return "unmerged"
    if standing_done:
        return "done"
    return "idle"


def find_shared_paths(ledgers: dict[str, LedgerSummary], workspaces: dict[str, str]) -> dict[str, list[dict[str, str]]]:
    """Which sessions are editing the same file in the same workspace.

    This is the branch that quietly ends up holding two features: you start one thread,
    move to another model, and both write the same file on one branch. Finding it while
    it is still two edits is the whole value — resolving it stays the operator's call.
    """
    shared: dict[str, list[dict[str, str]]] = {key: [] for key in ledgers}
    keys = sorted(ledgers)
    for index, left in enumerate(keys):
        for right in keys[index + 1 :]:
            if workspaces.get(left) != workspaces.get(right):
                continue
            overlap = ledgers[left].paths & ledgers[right].paths
            if not overlap:
                continue
            path = sorted(overlap)[0]
            shared[left].append({"sessionKey": right, "path": Path(path).name})
            shared[right].append({"sessionKey": left, "path": Path(path).name})
    return shared
