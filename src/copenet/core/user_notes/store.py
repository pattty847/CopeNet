"""Durable store for model-proposed USER.md edits awaiting operator review.

Mirrors the memory draft store: the model proposes a section delta with
``user.remember``; the operator approves it (merged into USER.md) or discards it.
Approved proposals are retained so they count toward the daily proposal cap.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import threading
from typing import Any
from uuid import uuid4

from copenet.core._json_store import read_json, write_json_atomic
from copenet.core.sessions.session_store import utc_now_iso


def _text(value: Any) -> str:
    return str(value or "").strip()


def _optional_text(value: Any) -> str | None:
    text = _text(value)
    return text or None


@dataclass(frozen=True)
class UserNoteProposal:
    id: str
    target_section: str        # the USER.md "## " section this delta belongs to
    summary: str               # one-line what/why for the operator
    body: str                  # markdown body to merge into the target section
    status: str = "draft"      # "draft" while awaiting review; "approved" once merged
    created_at: str = ""
    updated_at: str = ""
    last_session_key: str | None = None

    @classmethod
    def from_json(cls, raw: dict[str, Any]) -> "UserNoteProposal":
        created_at = _text(raw.get("createdAt") or raw.get("created_at")) or utc_now_iso()
        updated_at = _text(raw.get("updatedAt") or raw.get("updated_at")) or created_at
        status = _text(raw.get("status")).lower()
        return cls(
            id=_text(raw.get("id")) or f"usernote-{uuid4()}",
            target_section=_text(raw.get("targetSection") or raw.get("target_section")) or "Summary",
            summary=_text(raw.get("summary")) or "USER.md update",
            body=str(raw.get("body") or "").strip(),
            status=status if status in {"draft", "approved"} else "draft",
            created_at=created_at,
            updated_at=updated_at,
            last_session_key=_optional_text(raw.get("lastSessionKey") or raw.get("last_session_key")),
        )

    def to_json(self) -> dict[str, Any]:
        return asdict(self)

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "targetSection": self.target_section,
            "summary": self.summary,
            "body": self.body,
            "status": self.status,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
            "lastSessionKey": self.last_session_key,
        }


class UserNotesStore:
    """Atomic file-backed store for USER.md edit proposals."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def list_items(self) -> list[UserNoteProposal]:
        with self._lock:
            return self._load_unlocked()

    def get(self, note_id: str) -> UserNoteProposal | None:
        target = _text(note_id)
        if not target:
            return None
        with self._lock:
            for item in self._load_unlocked():
                if item.id == target:
                    return item
        return None

    def upsert(self, record: UserNoteProposal) -> UserNoteProposal:
        normalized = UserNoteProposal.from_json(record.to_json())
        with self._lock:
            rows = self._load_unlocked()
            next_rows: list[UserNoteProposal] = []
            replaced = False
            for item in rows:
                if item.id == normalized.id:
                    next_rows.append(normalized)
                    replaced = True
                else:
                    next_rows.append(item)
            if not replaced:
                next_rows.append(normalized)
            self._save_unlocked(next_rows)
        return normalized

    def delete(self, note_id: str) -> bool:
        target = _text(note_id)
        if not target:
            return False
        with self._lock:
            rows = self._load_unlocked()
            kept = [item for item in rows if item.id != target]
            if len(kept) == len(rows):
                return False
            self._save_unlocked(kept)
        return True

    def _load_unlocked(self) -> list[UserNoteProposal]:
        raw = read_json(self._path, [])
        payload = raw.get("items") if isinstance(raw, dict) else raw
        if not isinstance(payload, list):
            return []
        rows: list[UserNoteProposal] = []
        seen: set[str] = set()
        for item in payload:
            if not isinstance(item, dict):
                continue
            record = UserNoteProposal.from_json(item)
            if not record.id or record.id in seen:
                continue
            seen.add(record.id)
            rows.append(record)
        rows.sort(key=lambda item: item.created_at, reverse=True)
        return rows

    def _save_unlocked(self, rows: list[UserNoteProposal]) -> None:
        payload = {"items": [item.to_json() for item in sorted(rows, key=lambda item: item.created_at, reverse=True)]}
        write_json_atomic(self._path, payload)
