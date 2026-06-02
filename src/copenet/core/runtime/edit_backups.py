"""Pre-edit file backups so an operator can revert a model's write/edit.

Full-access edits apply immediately (the agent reads the file back to keep
working). To let the operator undo a specific change from the diff in the UI,
each write/edit records the file's prior content here, keyed by
(session_key, path, after_digest) — the digest the edit left the file at. Revert
restores the prior content only if the file is still in that exact state, so a
newer edit is never silently clobbered.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import threading
from typing import Any

from copenet._paths import default_edit_backups_dir
from copenet.core.sessions.session_store import utc_now_iso


def _safe_name(value: str) -> str:
    return "".join(ch for ch in value if ch.isalnum() or ch in ("-", "_", ".")).strip()


@dataclass
class EditBackupRecord:
    """One pre-edit snapshot of a file."""

    session_key: str
    path: str
    after_digest: str
    before_content: str
    run_id: str | None = None
    created_at: str = ""
    reverted_at: str | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "sessionKey": self.session_key,
            "path": self.path,
            "afterDigest": self.after_digest,
            "beforeContent": self.before_content,
            "runId": self.run_id,
            "createdAt": self.created_at or utc_now_iso(),
            "revertedAt": self.reverted_at,
        }

    @classmethod
    def from_json(cls, raw: dict[str, Any]) -> "EditBackupRecord":
        return cls(
            session_key=str(raw.get("sessionKey") or "").strip(),
            path=str(raw.get("path") or "").strip(),
            after_digest=str(raw.get("afterDigest") or "").strip(),
            before_content=str(raw.get("beforeContent") or ""),
            run_id=(str(raw.get("runId")).strip() or None) if raw.get("runId") is not None else None,
            created_at=str(raw.get("createdAt") or ""),
            reverted_at=(str(raw.get("revertedAt")).strip() or None) if raw.get("revertedAt") is not None else None,
        )


class EditBackupStore:
    """Append-only per-session store of pre-edit file content for revert."""

    def __init__(self, root_dir: Path | None = None) -> None:
        self._root_dir = root_dir if root_dir is not None else default_edit_backups_dir()
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
        path: str,
        after_digest: str,
        before_content: str,
        run_id: str | None = None,
    ) -> EditBackupRecord:
        """Append one pre-edit snapshot."""
        record = EditBackupRecord(
            session_key=session_key.strip(),
            path=path.strip(),
            after_digest=after_digest.strip(),
            before_content=before_content,
            run_id=run_id,
            created_at=utc_now_iso(),
        )
        ledger = self._path_for(record.session_key)
        line = json.dumps(record.to_json(), ensure_ascii=False)
        with self._lock:
            with ledger.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(line + "\n")
        return record

    def find(self, *, session_key: str, path: str, after_digest: str) -> EditBackupRecord | None:
        """Return the most recent non-reverted snapshot matching path + digest."""
        ledger = self._path_for(session_key)
        if not ledger.exists():
            return None
        with self._lock:
            lines = ledger.read_text(encoding="utf-8").splitlines()
        match: EditBackupRecord | None = None
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                record = EditBackupRecord.from_json(json.loads(line))
            except (json.JSONDecodeError, TypeError):
                continue
            if record.path == path.strip() and record.after_digest == after_digest.strip():
                match = record  # last match wins (most recent); a reverted marker clears it
        if match is None or match.reverted_at is not None:
            return None
        return match

    def mark_reverted(self, *, session_key: str, path: str, after_digest: str) -> None:
        """Append a reverted marker so the snapshot is not reused."""
        ledger = self._path_for(session_key)
        record = EditBackupRecord(
            session_key=session_key.strip(),
            path=path.strip(),
            after_digest=after_digest.strip(),
            before_content="",
            created_at=utc_now_iso(),
            reverted_at=utc_now_iso(),
        )
        line = json.dumps(record.to_json(), ensure_ascii=False)
        with self._lock:
            with ledger.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(line + "\n")
