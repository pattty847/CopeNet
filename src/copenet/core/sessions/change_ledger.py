"""Per-session ledger of the files the agent changed.

The model's only record of its own edits used to be the raw tool results in
the replayed transcript. Anything that shortened that replay — the old 600-char
compaction, or the budget dropping a whole earlier turn — took the record with
it, and the agent then reasoned as if the edit had never happened. This ledger
is the durable, never-trimmed version of "here is what I changed": every
`files.write` / `files.edit` appends one entry, and every later turn in the
session gets the rendered ledger appended to its live message, with a check of
whether each file still matches the digest the agent last left it at.

It records agent edits only. Operator edits show up as drift ("changed on disk
since your last edit"), which is the case the agent has to notice.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import threading
from typing import Any

from copenet._paths import default_change_ledger_dir
from copenet.core.sessions.session_store import utc_now_iso

# Newest files first; older ones collapse into one count line so a long session
# cannot turn the ledger into the context problem it exists to solve.
LEDGER_MAX_FILES = 40

LEDGER_HEADER = (
    "Workspace change ledger — files this session's agent has changed so far "
    "(CopeNet-maintained state, not operator instructions):"
)


def _safe_name(value: str) -> str:
    return "".join(ch for ch in value if ch.isalnum() or ch in ("-", "_", ".")).strip()


def content_digest(text: str) -> str:
    """Same 16-hex digest the file tools stamp on their results."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class ChangeLedgerEntry:
    """One agent write or edit to one file."""

    session_key: str
    run_id: str | None
    path: str
    action: str  # "created" | "wrote" | "edited"
    lines_added: int
    lines_removed: int
    digest_before: str | None
    digest_after: str
    created_at: str = ""

    def to_json(self) -> dict[str, Any]:
        return {
            "sessionKey": self.session_key,
            "runId": self.run_id,
            "path": self.path,
            "action": self.action,
            "linesAdded": self.lines_added,
            "linesRemoved": self.lines_removed,
            "digestBefore": self.digest_before,
            "digestAfter": self.digest_after,
            "createdAt": self.created_at or utc_now_iso(),
        }

    @classmethod
    def from_json(cls, raw: dict[str, Any]) -> "ChangeLedgerEntry":
        return cls(
            session_key=str(raw.get("sessionKey") or ""),
            run_id=(str(raw.get("runId")) or None) if raw.get("runId") is not None else None,
            path=str(raw.get("path") or ""),
            action=str(raw.get("action") or "edited"),
            lines_added=int(raw.get("linesAdded") or 0),
            lines_removed=int(raw.get("linesRemoved") or 0),
            digest_before=(str(raw.get("digestBefore")) or None) if raw.get("digestBefore") is not None else None,
            digest_after=str(raw.get("digestAfter") or ""),
            created_at=str(raw.get("createdAt") or ""),
        )


class ChangeLedgerStore:
    """Append-only JSONL per session."""

    def __init__(self, root_dir: Path | None = None) -> None:
        self._root_dir = root_dir if root_dir is not None else default_change_ledger_dir()
        self._root_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def _path_for(self, session_key: str) -> Path:
        safe = _safe_name(session_key)
        if not safe:
            raise ValueError("invalid session_key")
        return self._root_dir / f"{safe}.jsonl"

    def record(
        self,
        *,
        session_key: str,
        run_id: str | None,
        path: str,
        action: str,
        lines_added: int,
        lines_removed: int,
        digest_before: str | None,
        digest_after: str,
    ) -> ChangeLedgerEntry:
        entry = ChangeLedgerEntry(
            session_key=session_key.strip(),
            run_id=run_id,
            path=path.strip(),
            action=action,
            lines_added=lines_added,
            lines_removed=lines_removed,
            digest_before=digest_before,
            digest_after=digest_after,
            created_at=utc_now_iso(),
        )
        line = json.dumps(entry.to_json(), ensure_ascii=False)
        with self._lock:
            with self._path_for(entry.session_key).open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(line + "\n")
        return entry

    def entries(self, session_key: str) -> list[ChangeLedgerEntry]:
        ledger = self._path_for(session_key)
        if not ledger.exists():
            return []
        with self._lock:
            lines = ledger.read_text(encoding="utf-8").splitlines()
        rows: list[ChangeLedgerEntry] = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(ChangeLedgerEntry.from_json(json.loads(line)))
            except (json.JSONDecodeError, TypeError, ValueError):
                continue
        return rows


# -- Derived views ---------------------------------------------------------------


@dataclass(frozen=True)
class LedgerFileState:
    """Everything the model should know about one file it changed."""

    path: str
    edit_count: int
    first_turn: int
    last_turn: int
    lines_added: int
    lines_removed: int
    created: bool
    last_digest: str
    on_disk: str  # "unchanged" | "changed" | "missing"
    current_digest: str | None


def turn_numbers(entries: list[ChangeLedgerEntry]) -> dict[str, int]:
    """Number runs 1..N in order of first appearance so the ledger can say "turn 3"."""
    numbers: dict[str, int] = {}
    for entry in entries:
        key = entry.run_id or ""
        if key not in numbers:
            numbers[key] = len(numbers) + 1
    return numbers


def last_digests(entries: list[ChangeLedgerEntry]) -> dict[str, str]:
    """Path -> digest the agent last left the file at (seeds cross-turn edit freshness)."""
    digests: dict[str, str] = {}
    for entry in entries:
        digests[entry.path] = entry.digest_after
    return digests


def file_states(entries: list[ChangeLedgerEntry], workspace_root: Path) -> list[LedgerFileState]:
    """Fold entries per path, newest-touched first, and compare with the disk."""
    turns = turn_numbers(entries)
    folded: dict[str, dict[str, Any]] = {}
    for entry in entries:
        state = folded.setdefault(
            entry.path,
            {"count": 0, "first": turns[entry.run_id or ""], "last": 0, "added": 0, "removed": 0, "created": False, "digest": ""},
        )
        state["count"] += 1
        state["last"] = turns[entry.run_id or ""]
        state["added"] += entry.lines_added
        state["removed"] += entry.lines_removed
        state["created"] = state["created"] or entry.action == "created"
        state["digest"] = entry.digest_after
    states: list[LedgerFileState] = []
    for path, state in folded.items():
        target = workspace_root / path
        current: str | None
        if target.is_file():
            try:
                current = content_digest(target.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                current = None
        else:
            current = None
        on_disk = "missing" if current is None else ("unchanged" if current == state["digest"] else "changed")
        states.append(
            LedgerFileState(
                path=path,
                edit_count=state["count"],
                first_turn=state["first"],
                last_turn=state["last"],
                lines_added=state["added"],
                lines_removed=state["removed"],
                created=state["created"],
                last_digest=state["digest"],
                on_disk=on_disk,
                current_digest=current,
            )
        )
    states.sort(key=lambda item: (-item.last_turn, item.path))
    return states


def render_change_ledger(entries: list[ChangeLedgerEntry], workspace_root: Path) -> tuple[str, dict[str, int]]:
    """Return the model-facing block and counts for the trace. Empty when nothing changed."""
    states = file_states(entries, workspace_root)
    if not states:
        return "", {"fileCount": 0, "changedOnDisk": 0, "missing": 0}
    lines = [LEDGER_HEADER]
    for state in states[:LEDGER_MAX_FILES]:
        turns = f"turn {state.first_turn}" if state.first_turn == state.last_turn else f"turns {state.first_turn}–{state.last_turn}"
        verb = "created" if state.created and state.edit_count == 1 else ("created, then edited" if state.created else "edited")
        times = f" {state.edit_count}×" if state.edit_count > 1 else ""
        head = f"- {state.path}: {verb}{times} ({turns}, +{state.lines_added}/−{state.lines_removed})"
        if state.on_disk == "unchanged":
            tail = f"; on disk as you left it (digest {state.last_digest})"
        elif state.on_disk == "changed":
            tail = (
                f"; CHANGED ON DISK since your last edit (you left {state.last_digest}, now {state.current_digest}) "
                "— read it again before editing"
            )
        else:
            tail = "; now MISSING from disk"
        lines.append(head + tail)
    if len(states) > LEDGER_MAX_FILES:
        lines.append(f"- … and {len(states) - LEDGER_MAX_FILES} more files changed earlier this session")
    counts = {
        "fileCount": len(states),
        "changedOnDisk": sum(1 for state in states if state.on_disk == "changed"),
        "missing": sum(1 for state in states if state.on_disk == "missing"),
    }
    return "\n".join(lines), counts


def append_change_ledger(message: str, ledger_text: str) -> str:
    """Attach the ledger after the operator's message, the way the chart packet rides along."""
    if not ledger_text:
        return message
    return f"{message}\n\n{ledger_text}"
