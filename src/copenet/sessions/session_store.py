"""Session index storage for provider-backed chat continuity."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import threading
from typing import Any
from uuid import uuid4

from copenet._paths import default_sessions_dir


UTC = timezone.utc


def utc_now_iso() -> str:
    """Return current UTC timestamp in ISO-8601 format."""
    return datetime.now(UTC).isoformat()


@dataclass
class SessionIndexEntry:
    """Persistent session metadata entry."""

    session_id: str
    session_key: str
    provider: str
    provider_session_id: str | None
    created_at: str
    updated_at: str
    last_run_id: str | None = None
    in_flight_run_id: str | None = None

    @classmethod
    def from_json(cls, raw: dict[str, Any]) -> SessionIndexEntry:
        """Create entry from storage dictionary."""
        provider_session_id_raw = raw.get("provider_session_id") or raw.get("providerSessionId")
        last_run_id_raw = raw.get("last_run_id") or raw.get("lastRunId")
        in_flight_run_id_raw = raw.get("in_flight_run_id") or raw.get("inFlightRunId")

        return cls(
            session_id=str(raw.get("session_id") or raw.get("sessionId") or "").strip()
            or str(raw.get("session_key") or raw.get("sessionKey") or "").strip(),
            session_key=str(raw.get("session_key") or raw.get("sessionKey") or "").strip(),
            provider=str(raw.get("provider") or "").strip(),
            provider_session_id=(str(provider_session_id_raw).strip() if provider_session_id_raw else None),
            created_at=str(raw.get("created_at") or raw.get("createdAt") or utc_now_iso()),
            updated_at=str(raw.get("updated_at") or raw.get("updatedAt") or utc_now_iso()),
            last_run_id=(str(last_run_id_raw).strip() if last_run_id_raw else None),
            in_flight_run_id=(str(in_flight_run_id_raw).strip() if in_flight_run_id_raw else None),
        )

    def to_json(self) -> dict[str, Any]:
        """Convert entry to JSON-friendly dictionary."""
        return asdict(self)


class SessionStore:
    """Thread-safe JSON-backed session index."""

    def __init__(self, path: Path | None = None) -> None:
        base = default_sessions_dir() if path is None else path.parent
        self._path = path if path is not None else (base / "index.json")
        self._lock = threading.RLock()
        self._path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def path(self) -> Path:
        """Return backing file path."""
        return self._path

    def list_sessions(self) -> list[SessionIndexEntry]:
        """Return all sessions sorted by most recent update."""
        with self._lock:
            entries = list(self._load_map().values())
        entries.sort(key=lambda item: item.updated_at, reverse=True)
        return entries

    def get(self, session_key: str) -> SessionIndexEntry | None:
        """Fetch a session entry by key."""
        with self._lock:
            return self._load_map().get(session_key.strip())

    def resolve_or_create(self, session_key: str, provider: str) -> SessionIndexEntry:
        """Resolve existing session or create a new one."""
        normalized_key = session_key.strip()
        normalized_provider = provider.strip()
        if not normalized_key:
            raise ValueError("session_key is required")
        if not normalized_provider:
            raise ValueError("provider is required")

        with self._lock:
            sessions = self._load_map()
            existing = sessions.get(normalized_key)
            if existing is not None:
                if existing.provider != normalized_provider:
                    existing.provider = normalized_provider
                existing.updated_at = utc_now_iso()
                sessions[normalized_key] = existing
                self._save_map(sessions)
                return existing

            now = utc_now_iso()
            created = SessionIndexEntry(
                session_id=str(uuid4()),
                session_key=normalized_key,
                provider=normalized_provider,
                provider_session_id=None,
                created_at=now,
                updated_at=now,
                last_run_id=None,
                in_flight_run_id=None,
            )
            sessions[normalized_key] = created
            self._save_map(sessions)
            return created

    def update_provider_session_id(self, session_key: str, provider_session_id: str) -> SessionIndexEntry:
        """Persist provider session ID (for resume continuity)."""
        normalized_key = session_key.strip()
        normalized_id = provider_session_id.strip()
        if not normalized_key:
            raise ValueError("session_key is required")
        if not normalized_id:
            raise ValueError("provider_session_id is required")

        with self._lock:
            sessions = self._load_map()
            entry = sessions.get(normalized_key)
            if entry is None:
                raise KeyError(f"unknown session_key: {normalized_key}")
            entry.provider_session_id = normalized_id
            entry.updated_at = utc_now_iso()
            sessions[normalized_key] = entry
            self._save_map(sessions)
            return entry

    def mark_run_started(self, session_key: str, run_id: str | None = None) -> SessionIndexEntry:
        """Mark run start and lock the session as in-flight."""
        normalized_key = session_key.strip()
        if not normalized_key:
            raise ValueError("session_key is required")

        run = (run_id or str(uuid4())).strip()
        if not run:
            raise ValueError("run_id is required")

        with self._lock:
            sessions = self._load_map()
            entry = sessions.get(normalized_key)
            if entry is None:
                raise KeyError(f"unknown session_key: {normalized_key}")
            if entry.in_flight_run_id and entry.in_flight_run_id != run:
                raise RuntimeError(f"session is in flight: {entry.in_flight_run_id}")
            entry.in_flight_run_id = run
            entry.last_run_id = run
            entry.updated_at = utc_now_iso()
            sessions[normalized_key] = entry
            self._save_map(sessions)
            return entry

    def mark_run_finished(self, session_key: str, run_id: str) -> SessionIndexEntry:
        """Clear in-flight marker for a completed run."""
        normalized_key = session_key.strip()
        normalized_run = run_id.strip()
        if not normalized_key:
            raise ValueError("session_key is required")
        if not normalized_run:
            raise ValueError("run_id is required")

        with self._lock:
            sessions = self._load_map()
            entry = sessions.get(normalized_key)
            if entry is None:
                raise KeyError(f"unknown session_key: {normalized_key}")
            if entry.in_flight_run_id == normalized_run:
                entry.in_flight_run_id = None
            entry.updated_at = utc_now_iso()
            sessions[normalized_key] = entry
            self._save_map(sessions)
            return entry

    def _load_map(self) -> dict[str, SessionIndexEntry]:
        if not self._path.exists():
            return {}

        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

        items = raw.get("sessions") if isinstance(raw, dict) else None
        if not isinstance(items, list):
            return {}

        result: dict[str, SessionIndexEntry] = {}
        for item in items:
            if not isinstance(item, dict):
                continue
            entry = SessionIndexEntry.from_json(item)
            if not entry.session_key:
                continue
            result[entry.session_key] = entry
        return result

    def _save_map(self, sessions: dict[str, SessionIndexEntry]) -> None:
        payload = {
            "sessions": [entry.to_json() for entry in sessions.values()],
        }
        tmp_path = self._path.with_suffix(self._path.suffix + ".tmp")
        tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_path.replace(self._path)
