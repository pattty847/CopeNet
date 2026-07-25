"""Atomic append-only Fleet room storage."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import threading
from typing import Any
from uuid import uuid4


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class FleetRoomStore:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.RLock()
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def list_rooms(self, *, include_archived: bool = False) -> list[dict[str, Any]]:
        with self._lock:
            rooms = list(self._load().values())
        if not include_archived:
            rooms = [room for room in rooms if room.get("status") != "archived"]
        return sorted(rooms, key=lambda room: str(room.get("updatedAt") or ""), reverse=True)

    def get(self, room_id: str) -> dict[str, Any] | None:
        with self._lock:
            room = self._load().get(room_id.strip())
            return json.loads(json.dumps(room)) if room is not None else None

    def create(
        self,
        *,
        title: str,
        participants: dict[str, dict[str, Any]],
        room_id: str | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            rooms = self._load()
            if any(room.get("status") == "active" for room in rooms.values()):
                raise ValueError("only one active Fleet room is allowed")
            room_id = room_id or f"fleet-{uuid4().hex[:10]}"
            if room_id in rooms:
                raise ValueError(f"Fleet room already exists: {room_id}")
            now = _now()
            room = {
                "roomId": room_id,
                "title": title.strip() or "Fleet Room",
                "status": "active",
                "mode": "manual",
                "participants": participants,
                "deliveryCursors": {participant_id: 0 for participant_id in participants},
                "events": [],
                "createdAt": now,
                "updatedAt": now,
            }
            rooms[room_id] = room
            self._save(rooms)
            return json.loads(json.dumps(room))

    def append_event(
        self,
        room_id: str,
        *,
        kind: str,
        author: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            rooms = self._load()
            room = self._require_active(rooms, room_id)
            event = self._new_event(room, kind=kind, author=author, content=content, metadata=metadata)
            self._save(rooms)
            return json.loads(json.dumps(event))

    def commit_lane_turn(
        self,
        room_id: str,
        *,
        participant_id: str,
        delivered_through: int,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Append the answer and advance its cursor in the same atomic write."""
        with self._lock:
            rooms = self._load()
            room = self._require_active(rooms, room_id)
            event = self._new_event(
                room,
                kind="assistant",
                author=participant_id,
                content=content,
                metadata=metadata,
            )
            room["deliveryCursors"][participant_id] = max(
                int(room["deliveryCursors"].get(participant_id) or 0),
                int(delivered_through),
            )
            self._save(rooms)
            return json.loads(json.dumps(event))

    def archive(self, room_id: str) -> dict[str, Any]:
        with self._lock:
            rooms = self._load()
            room = rooms.get(room_id.strip())
            if room is None:
                raise KeyError(f"unknown Fleet room: {room_id}")
            room["status"] = "archived"
            room["updatedAt"] = _now()
            self._save(rooms)
            return json.loads(json.dumps(room))

    @staticmethod
    def _require_active(rooms: dict[str, dict[str, Any]], room_id: str) -> dict[str, Any]:
        room = rooms.get(room_id.strip())
        if room is None:
            raise KeyError(f"unknown Fleet room: {room_id}")
        if room.get("status") != "active":
            raise ValueError(f"Fleet room is not active: {room_id}")
        return room

    @staticmethod
    def _new_event(
        room: dict[str, Any],
        *,
        kind: str,
        author: str,
        content: str,
        metadata: dict[str, Any] | None,
    ) -> dict[str, Any]:
        events = room.setdefault("events", [])
        event = {
            "eventId": str(uuid4()),
            "seq": int(events[-1]["seq"]) + 1 if events else 1,
            "kind": kind,
            "author": author,
            "content": content,
            "metadata": metadata or {},
            "createdAt": _now(),
        }
        events.append(event)
        room["updatedAt"] = event["createdAt"]
        return event

    def _load(self) -> dict[str, dict[str, Any]]:
        if not self._path.exists():
            return {}
        raw = json.loads(self._path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise RuntimeError("Fleet room store must be a JSON object")
        return raw

    def _save(self, rooms: dict[str, dict[str, Any]]) -> None:
        tmp = self._path.with_suffix(f"{self._path.suffix}.tmp")
        tmp.write_text(json.dumps(rooms, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(self._path)
