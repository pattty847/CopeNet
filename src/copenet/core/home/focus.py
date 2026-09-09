"""The operator's focus list: a checklist, a notes pad, and the Quick Launch layout.

Small, durable, and deliberately server-side rather than in browser storage: the same desk
is read from the Mac and from the phone over Tailscale, and a checklist that disagreed
between them would be worse than no checklist.

This is operator-authored text, never model-authored. Nothing here is a memory item — memory
is what CopeNet learned, this is what the operator wrote down — so it stays out of the
memory store and out of prompts.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from copenet.core._json_store import read_json, write_json_atomic

MAX_ITEMS = 24
MAX_TEXT = 400
MAX_NOTES = 8_000


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class FocusItem:
    item_id: str
    text: str
    done: bool = False
    created_at: str = field(default_factory=_now)

    def to_public_dict(self) -> dict:
        return {"itemId": self.item_id, "text": self.text, "done": self.done, "createdAt": self.created_at}

    @classmethod
    def from_json(cls, raw: dict) -> "FocusItem":
        return cls(
            item_id=str(raw.get("itemId") or raw.get("item_id") or uuid.uuid4().hex[:12]),
            text=str(raw.get("text") or "")[:MAX_TEXT],
            done=bool(raw.get("done")),
            created_at=str(raw.get("createdAt") or raw.get("created_at") or _now()),
        )


@dataclass
class FocusState:
    items: list[FocusItem] = field(default_factory=list)
    notes: str = ""
    """Quick Launch tile ids in the operator's chosen order. Empty means "the default set",
    which is what lets a new tile appear for an operator who never customised anything."""
    quick_launch: list[str] = field(default_factory=list)
    updated_at: str = field(default_factory=_now)

    def to_public_dict(self) -> dict:
        return {
            "items": [item.to_public_dict() for item in self.items],
            "notes": self.notes,
            "quickLaunch": list(self.quick_launch),
            "updatedAt": self.updated_at,
        }


class FocusStore:
    """One JSON file, read and rewritten whole. The document is a few hundred bytes."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def load(self) -> FocusState:
        raw = read_json(self._path, fallback={})
        if not isinstance(raw, dict):
            return FocusState()
        items = raw.get("items")
        return FocusState(
            items=[FocusItem.from_json(entry) for entry in items if isinstance(entry, dict)]
            if isinstance(items, list)
            else [],
            notes=str(raw.get("notes") or "")[:MAX_NOTES],
            quick_launch=[str(tile) for tile in raw.get("quickLaunch") or [] if str(tile).strip()],
            updated_at=str(raw.get("updatedAt") or _now()),
        )

    def _save(self, state: FocusState) -> FocusState:
        state.updated_at = _now()
        write_json_atomic(self._path, state.to_public_dict())
        return state

    def add_item(self, text: str) -> FocusState:
        cleaned = " ".join(str(text or "").split())[:MAX_TEXT]
        if not cleaned:
            raise ValueError("focus item text is required")
        state = self.load()
        if len(state.items) >= MAX_ITEMS:
            raise ValueError(f"focus list is full ({MAX_ITEMS} items) — clear something first")
        state.items.append(FocusItem(item_id=uuid.uuid4().hex[:12], text=cleaned))
        return self._save(state)

    def set_item(self, item_id: str, *, text: str | None = None, done: bool | None = None) -> FocusState:
        state = self.load()
        for item in state.items:
            if item.item_id != item_id:
                continue
            if text is not None:
                cleaned = " ".join(str(text).split())[:MAX_TEXT]
                if not cleaned:
                    raise ValueError("focus item text cannot be blank")
                item.text = cleaned
            if done is not None:
                item.done = bool(done)
            return self._save(state)
        raise KeyError(item_id)

    def remove_item(self, item_id: str) -> FocusState:
        state = self.load()
        remaining = [item for item in state.items if item.item_id != item_id]
        if len(remaining) == len(state.items):
            raise KeyError(item_id)
        state.items = remaining
        return self._save(state)

    def clear_done(self) -> FocusState:
        state = self.load()
        state.items = [item for item in state.items if not item.done]
        return self._save(state)

    def set_notes(self, notes: str) -> FocusState:
        state = self.load()
        state.notes = str(notes or "")[:MAX_NOTES]
        return self._save(state)

    def set_quick_launch(self, tiles: list[str]) -> FocusState:
        state = self.load()
        seen: set[str] = set()
        ordered: list[str] = []
        for tile in tiles:
            key = str(tile).strip()
            if key and key not in seen:
                seen.add(key)
                ordered.append(key)
        state.quick_launch = ordered
        return self._save(state)


__all__ = ["FocusItem", "FocusState", "FocusStore"]
