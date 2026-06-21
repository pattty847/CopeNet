"""Durable Telegram chat-to-session routing storage."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import threading
from typing import Any
from uuid import uuid4

from copenet.core._json_store import read_json, write_json_atomic


def _required_text(raw: dict[str, Any], key: str) -> str:
    value = raw.get(key)
    return str(value).strip() if value is not None else ""


def _optional_text(raw: dict[str, Any], key: str) -> str | None:
    value = raw.get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


@dataclass(frozen=True)
class TelegramSessionRouteRecord:
    id: str
    platform: str
    chat_id: str
    thread_id: str | None
    session_key: str
    title_override: str | None = None

    @classmethod
    def from_json(cls, raw: dict[str, Any]) -> "TelegramSessionRouteRecord":
        return cls(
            id=_required_text(raw, "id"),
            platform=_required_text(raw, "platform") or "telegram",
            chat_id=_required_text(raw, "chat_id") or _required_text(raw, "chatId"),
            thread_id=_optional_text(raw, "thread_id") or _optional_text(raw, "threadId"),
            session_key=_required_text(raw, "session_key") or _required_text(raw, "sessionKey"),
            title_override=_optional_text(raw, "title_override") or _optional_text(raw, "titleOverride"),
        )

    def to_json(self) -> dict[str, Any]:
        return asdict(self)

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "platform": self.platform,
            "chatId": self.chat_id,
            "threadId": self.thread_id,
            "sessionKey": self.session_key,
            "titleOverride": self.title_override,
        }


class TelegramSessionRouteStore:
    """Thread-safe JSON store for Telegram chat/thread to session mappings."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def list_routes(self) -> list[TelegramSessionRouteRecord]:
        with self._lock:
            return self._load_unlocked()

    def find_route(self, *, platform: str, chat_id: str, thread_id: str | None) -> TelegramSessionRouteRecord | None:
        normalized_platform = str(platform or "telegram").strip() or "telegram"
        normalized_chat_id = str(chat_id or "").strip()
        normalized_thread_id = str(thread_id).strip() if thread_id is not None and str(thread_id).strip() else None
        with self._lock:
            for route in self._load_unlocked():
                if (
                    route.platform == normalized_platform
                    and route.chat_id == normalized_chat_id
                    and route.thread_id == normalized_thread_id
                ):
                    return route
        return None

    def upsert_route(self, route: TelegramSessionRouteRecord) -> list[TelegramSessionRouteRecord]:
        normalized = _normalize_route(route)
        with self._lock:
            current = self._load_unlocked()
            rows: list[TelegramSessionRouteRecord] = []
            replaced = False
            for item in current:
                same_route_key = (
                    item.platform == normalized.platform
                    and item.chat_id == normalized.chat_id
                    and item.thread_id == normalized.thread_id
                )
                if item.id == normalized.id or same_route_key:
                    rows.append(normalized)
                    replaced = True
                else:
                    rows.append(item)
            if not replaced:
                rows.append(normalized)
            self._save_unlocked(rows)
            return rows

    def delete_route(self, route_id: str) -> list[TelegramSessionRouteRecord]:
        target_id = str(route_id or "").strip()
        with self._lock:
            current = self._load_unlocked()
            rows = [item for item in current if item.id != target_id]
            self._save_unlocked(rows)
            return rows

    def _load_unlocked(self) -> list[TelegramSessionRouteRecord]:
        raw = read_json(self._path, [])
        payload = raw.get("routes") if isinstance(raw, dict) and isinstance(raw.get("routes"), list) else raw
        if not isinstance(payload, list):
            return []
        rows: list[TelegramSessionRouteRecord] = []
        seen_ids: set[str] = set()
        seen_route_keys: set[tuple[str, str, str | None]] = set()
        for item in payload:
            if not isinstance(item, dict):
                continue
            record = _normalize_route(TelegramSessionRouteRecord.from_json(item))
            route_key = (record.platform, record.chat_id, record.thread_id)
            if not record.id or not record.chat_id or not record.session_key or record.id in seen_ids or route_key in seen_route_keys:
                continue
            rows.append(record)
            seen_ids.add(record.id)
            seen_route_keys.add(route_key)
        return rows

    def _save_unlocked(self, routes: list[TelegramSessionRouteRecord]) -> None:
        payload = {"routes": [item.to_json() for item in routes]}
        write_json_atomic(self._path, payload, trailing_newline=False)


def _normalize_route(route: TelegramSessionRouteRecord) -> TelegramSessionRouteRecord:
    return TelegramSessionRouteRecord(
        id=route.id.strip() or f"route-{uuid4()}",
        platform=route.platform.strip() or "telegram",
        chat_id=route.chat_id.strip(),
        thread_id=route.thread_id.strip() if route.thread_id else None,
        session_key=route.session_key.strip(),
        title_override=route.title_override.strip() if route.title_override else None,
    )
