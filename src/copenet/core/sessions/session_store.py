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


def _required_str(raw: dict[str, Any], key: str) -> str:
    value = raw.get(key)
    return str(value).strip() if value is not None else ""


def _optional_str(raw: dict[str, Any], key: str) -> str | None:
    value = raw.get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


@dataclass
class SessionIndexEntry:
    """Persistent session metadata entry."""

    session_id: str
    session_key: str
    title: str | None
    provider: str
    model: str | None
    system_prompt_id: str | None
    task_prompt_id: str | None
    archived: bool
    provider_session_id: str | None
    created_at: str
    updated_at: str
    last_run_id: str | None = None
    in_flight_run_id: str | None = None

    @classmethod
    def from_json(cls, raw: dict[str, Any]) -> SessionIndexEntry:
        """Create entry from storage dictionary."""
        # Disk format is snake_case. Wire format is camelCase in RPC payloads.
        session_key = _required_str(raw, "session_key")

        return cls(
            session_id=_required_str(raw, "session_id") or session_key,
            session_key=session_key,
            title=_optional_str(raw, "title"),
            provider=_required_str(raw, "provider"),
            model=_optional_str(raw, "model"),
            system_prompt_id=_optional_str(raw, "system_prompt_id"),
            task_prompt_id=_optional_str(raw, "task_prompt_id"),
            archived=bool(raw.get("archived", False)),
            provider_session_id=_optional_str(raw, "provider_session_id"),
            created_at=_required_str(raw, "created_at") or utc_now_iso(),
            updated_at=_required_str(raw, "updated_at") or utc_now_iso(),
            last_run_id=_optional_str(raw, "last_run_id"),
            in_flight_run_id=_optional_str(raw, "in_flight_run_id"),
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

    def list_sessions(self, include_archived: bool = False) -> list[SessionIndexEntry]:
        """Return all sessions sorted by most recent update."""
        with self._lock:
            entries = list(self._load_map().values())
        if not include_archived:
            entries = [entry for entry in entries if not entry.archived]
        entries.sort(key=lambda item: item.updated_at, reverse=True)
        return entries

    def get(self, session_key: str) -> SessionIndexEntry | None:
        """Fetch a session entry by key."""
        with self._lock:
            return self._load_map().get(session_key.strip())

    def create_session(
        self,
        session_key: str,
        provider: str,
        model: str | None = None,
        title: str | None = None,
        system_prompt_id: str | None = None,
        task_prompt_id: str | None = None,
    ) -> SessionIndexEntry:
        """Create a new locked session."""
        normalized_key = session_key.strip()
        normalized_provider = provider.strip()
        normalized_model = model.strip() if model else None
        normalized_title = title.strip() if title else None
        normalized_system_prompt_id = system_prompt_id.strip() if system_prompt_id else None
        normalized_task_prompt_id = task_prompt_id.strip() if task_prompt_id else None
        if not normalized_key:
            raise ValueError("session_key is required")
        if not normalized_provider:
            raise ValueError("provider is required")

        with self._lock:
            sessions = self._load_map()
            existing = sessions.get(normalized_key)
            if existing is not None:
                raise ValueError(f"session already exists: {normalized_key}")

            now = utc_now_iso()
            created = SessionIndexEntry(
                session_id=str(uuid4()),
                session_key=normalized_key,
                title=normalized_title,
                provider=normalized_provider,
                model=normalized_model,
                system_prompt_id=normalized_system_prompt_id,
                task_prompt_id=normalized_task_prompt_id,
                archived=False,
                provider_session_id=None,
                created_at=now,
                updated_at=now,
                last_run_id=None,
                in_flight_run_id=None,
            )
            sessions[normalized_key] = created
            self._save_map(sessions)
            return created

    def create_generated_session_key(self, provider: str, model: str | None = None) -> str:
        """Generate a readable unique session key."""
        provider_slug = "".join(ch if ch.isalnum() else "-" for ch in provider.lower()).strip("-") or "chat"
        model_slug = "".join(ch if ch.isalnum() else "-" for ch in (model or "default").lower()).strip("-") or "default"
        prefix = f"{provider_slug}-{model_slug}"[:48].strip("-") or "chat"

        with self._lock:
            sessions = self._load_map()
            if prefix not in sessions:
                return prefix
            counter = 2
            while f"{prefix}-{counter}" in sessions:
                counter += 1
            return f"{prefix}-{counter}"

    def resolve_or_create(
        self,
        session_key: str,
        provider: str,
        model: str | None = None,
        system_prompt_id: str | None = None,
        task_prompt_id: str | None = None,
    ) -> SessionIndexEntry:
        """Resolve an existing session or create a new one when missing."""
        normalized_key = session_key.strip()
        if not normalized_key:
            raise ValueError("session_key is required")
        existing = self.get(normalized_key)
        if existing is not None:
            return existing
        return self.create_session(
            session_key=normalized_key,
            provider=provider,
            model=model,
            system_prompt_id=system_prompt_id,
            task_prompt_id=task_prompt_id,
        )

    def assert_session_binding(
        self,
        session_key: str,
        provider: str,
        model: str | None = None,
        system_prompt_id: str | None = None,
        task_prompt_id: str | None = None,
    ) -> SessionIndexEntry:
        """Ensure the requested provider/model matches the locked session binding."""
        normalized_key = session_key.strip()
        normalized_provider = provider.strip()
        normalized_model = model.strip() if model else None
        normalized_system_prompt_id = system_prompt_id.strip() if system_prompt_id else None
        normalized_task_prompt_id = task_prompt_id.strip() if task_prompt_id else None
        if not normalized_key:
            raise ValueError("session_key is required")

        with self._lock:
            sessions = self._load_map()
            entry = sessions.get(normalized_key)
            if entry is None:
                raise KeyError(f"unknown session_key: {normalized_key}")
            if entry.archived:
                raise RuntimeError(f"session is archived: {normalized_key}")
            if entry.provider != normalized_provider:
                raise RuntimeError(
                    f"session is locked to provider {entry.provider}; requested {normalized_provider}"
                )
            if entry.model != normalized_model:
                raise RuntimeError(
                    f"session is locked to model {entry.model or 'default'}; requested {normalized_model or 'default'}"
                )
            if entry.system_prompt_id and entry.system_prompt_id != normalized_system_prompt_id:
                raise RuntimeError(
                    f"session is locked to profile {entry.system_prompt_id}; requested {normalized_system_prompt_id or 'none'}"
                )
            if entry.task_prompt_id and entry.task_prompt_id != normalized_task_prompt_id:
                raise RuntimeError(
                    f"session is locked to task mode {entry.task_prompt_id}; requested {normalized_task_prompt_id or 'none'}"
                )
            return entry

    def rename_session(self, session_key: str, title: str | None) -> SessionIndexEntry:
        """Update the session display title without changing its identity key."""
        normalized_key = session_key.strip()
        normalized_title = title.strip() if title else None
        if not normalized_key:
            raise ValueError("session_key is required")

        with self._lock:
            sessions = self._load_map()
            entry = sessions.get(normalized_key)
            if entry is None:
                raise KeyError(f"unknown session_key: {normalized_key}")
            entry.title = normalized_title
            entry.updated_at = utc_now_iso()
            sessions[normalized_key] = entry
            self._save_map(sessions)
            return entry

    def set_archived(self, session_key: str, archived: bool) -> SessionIndexEntry:
        """Archive or restore a session."""
        normalized_key = session_key.strip()
        if not normalized_key:
            raise ValueError("session_key is required")

        with self._lock:
            sessions = self._load_map()
            entry = sessions.get(normalized_key)
            if entry is None:
                raise KeyError(f"unknown session_key: {normalized_key}")
            entry.archived = archived
            entry.updated_at = utc_now_iso()
            sessions[normalized_key] = entry
            self._save_map(sessions)
            return entry

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
