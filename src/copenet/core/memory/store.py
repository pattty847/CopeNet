"""Durable user-visible memory records."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import threading
from typing import Any, Literal
from uuid import uuid4

from copenet.core.sessions.session_store import utc_now_iso

MemoryCategory = Literal["preference", "project_convention", "ongoing_priority", "fact"]


def _text(value: Any) -> str:
    return str(value or "").strip()


def _optional_text(value: Any) -> str | None:
    text = _text(value)
    return text or None


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [text for item in value if (text := _text(item))]


@dataclass(frozen=True)
class MemoryRecord:
    id: str
    category: MemoryCategory
    title: str
    summary: str
    detail: str | None = None
    tags: tuple[str, ...] = ()
    source: str = "explicit"
    confidence: float = 0.8
    created_at: str = utc_now_iso()
    updated_at: str = utc_now_iso()
    archived: bool = False
    # "active" once committed; "draft" while a model-proposed memory awaits operator
    # approval. Drafts are excluded from relevance injection and the default list.
    status: str = "active"
    last_session_key: str | None = None

    @classmethod
    def from_json(cls, raw: dict[str, Any]) -> "MemoryRecord":
        category = _text(raw.get("category") or raw.get("kind") or "")
        if category not in {"preference", "project_convention", "ongoing_priority", "fact"}:
            category = "fact"
        created_at = _text(raw.get("createdAt") or raw.get("created_at")) or utc_now_iso()
        updated_at = _text(raw.get("updatedAt") or raw.get("updated_at")) or created_at
        return cls(
            id=_text(raw.get("id")) or f"memory-{uuid4()}",
            category=category,
            title=_text(raw.get("title")) or _text(raw.get("summary"))[:80] or "Memory",
            summary=_text(raw.get("summary")) or _text(raw.get("title")) or "Memory item",
            detail=_optional_text(raw.get("detail")),
            tags=tuple(_string_list(raw.get("tags"))),
            source=_text(raw.get("source")) or "explicit",
            confidence=float(raw.get("confidence") or 0.8),
            created_at=created_at,
            updated_at=updated_at,
            archived=bool(raw.get("archived")),
            status=(_text(raw.get("status")).lower() if _text(raw.get("status")).lower() in {"active", "draft"} else "active"),
            last_session_key=_optional_text(raw.get("lastSessionKey") or raw.get("last_session_key")),
        )

    def to_json(self) -> dict[str, Any]:
        return asdict(self)

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "category": self.category,
            "title": self.title,
            "summary": self.summary,
            "detail": self.detail,
            "tags": list(self.tags),
            "source": self.source,
            "confidence": self.confidence,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
            "archived": self.archived,
            "status": self.status,
            "lastSessionKey": self.last_session_key,
        }


class MemoryStore:
    """Atomic file-backed store for durable memory items."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def list_items(self, *, include_archived: bool = False) -> list[MemoryRecord]:
        with self._lock:
            rows = self._load_unlocked()
        return rows if include_archived else [item for item in rows if not item.archived]

    def get(self, memory_id: str) -> MemoryRecord | None:
        target = _text(memory_id)
        if not target:
            return None
        with self._lock:
            for item in self._load_unlocked():
                if item.id == target:
                    return item
        return None

    def upsert(self, record: MemoryRecord) -> MemoryRecord:
        normalized = MemoryRecord.from_json(record.to_json())
        with self._lock:
            rows = self._load_unlocked()
            next_rows: list[MemoryRecord] = []
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

    def archive(self, memory_id: str, *, archived: bool = True) -> MemoryRecord | None:
        current = self.get(memory_id)
        if current is None:
            return None
        updated = MemoryRecord(
            id=current.id,
            category=current.category,
            title=current.title,
            summary=current.summary,
            detail=current.detail,
            tags=current.tags,
            source=current.source,
            confidence=current.confidence,
            created_at=current.created_at,
            updated_at=utc_now_iso(),
            archived=archived,
            status=current.status,
            last_session_key=current.last_session_key,
        )
        return self.upsert(updated)

    def delete(self, memory_id: str) -> bool:
        target = _text(memory_id)
        if not target:
            return False
        with self._lock:
            rows = self._load_unlocked()
            kept = [item for item in rows if item.id != target]
            if len(kept) == len(rows):
                return False
            self._save_unlocked(kept)
        return True

    def _load_unlocked(self) -> list[MemoryRecord]:
        if not self._path.exists():
            return []
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        payload = raw.get("items") if isinstance(raw, dict) else raw
        if not isinstance(payload, list):
            return []
        rows: list[MemoryRecord] = []
        seen: set[str] = set()
        for item in payload:
            if not isinstance(item, dict):
                continue
            record = MemoryRecord.from_json(item)
            if not record.id or record.id in seen:
                continue
            seen.add(record.id)
            rows.append(record)
        rows.sort(key=lambda item: item.updated_at, reverse=True)
        return rows

    def _save_unlocked(self, rows: list[MemoryRecord]) -> None:
        payload = {"items": [item.to_json() for item in sorted(rows, key=lambda item: item.updated_at, reverse=True)]}
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp.replace(self._path)
