"""Session index storage for provider-backed chat continuity."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

from copenet._paths import default_sessions_dir
from copenet.core._json_store import _path_lock


UTC = timezone.utc


def _is_safe_store_key(value: str) -> bool:
    """True when `value` survives every durable per-session store's filename sanitizer unchanged.

    The runs/artifacts/state stores each turn a session_key into a filename via a sanitizer
    that deletes any character outside [A-Za-z0-9._-]. This index itself accepts any
    non-empty string as a dict key, so two different keys that sanitize to the same string
    (e.g. "a/b" and "ab") would silently share one runs/artifacts/state file across two
    otherwise-distinct sessions. Reject anything that isn't already sanitizer-stable here,
    at the single session-creation boundary, so an accepted key can never collide downstream.
    """
    return bool(value) and all(ch.isalnum() or ch in ("-", "_", ".") for ch in value)


class SessionIndexError(RuntimeError):
    """Raised when the session index exists but cannot be parsed.

    We fail loud rather than treating a corrupt index as empty, because every
    mutator does load->modify->save: a silent empty load would let the next
    write atomically overwrite the real index with a near-empty file, orphaning
    every session. The corrupt file is backed up before we raise.
    """


def utc_now_iso() -> str:
    """Return current UTC timestamp in ISO-8601 format."""
    return datetime.now(UTC).isoformat()


def _effective_task_mode(task_prompt_id: str | None) -> str:
    """Canonical task-mode id for lock comparison.

    Mirrors ``policy_for_task_mode``: a missing/blank task mode is "none"
    (guarded). The binding lock must compare EFFECTIVE modes, because task mode
    gates tool policy — full-access grants repo-write + unrestricted shell. A
    session created with a null task mode must not be silently escalated to
    full-access on a later send, which a raw ``if entry.task_prompt_id and ...``
    check (skipped when the stored value is null) would have allowed.
    """
    return (task_prompt_id or "none").strip().lower() or "none"


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
    persona_id: str | None
    persona_flavor_id: str | None
    persona_privacy_tier: str | None
    workspace_root: str | None
    archived: bool
    provider_session_id: str | None
    created_at: str
    updated_at: str
    last_run_id: str | None = None
    in_flight_run_id: str | None = None
    session_type: str = "standard"
    parent_session_key: str | None = None
    participant_id: str | None = None

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
            persona_id=_optional_str(raw, "persona_id"),
            persona_flavor_id=_optional_str(raw, "persona_flavor_id"),
            persona_privacy_tier=_optional_str(raw, "persona_privacy_tier"),
            workspace_root=_optional_str(raw, "workspace_root"),
            archived=bool(raw.get("archived", False)),
            provider_session_id=_optional_str(raw, "provider_session_id"),
            created_at=_required_str(raw, "created_at") or utc_now_iso(),
            updated_at=_required_str(raw, "updated_at") or utc_now_iso(),
            last_run_id=_optional_str(raw, "last_run_id"),
            in_flight_run_id=_optional_str(raw, "in_flight_run_id"),
            session_type=_optional_str(raw, "session_type") or "standard",
            parent_session_key=_optional_str(raw, "parent_session_key"),
            participant_id=_optional_str(raw, "participant_id"),
        )

    def to_json(self) -> dict[str, Any]:
        """Convert entry to JSON-friendly dictionary."""
        return asdict(self)


class SessionStore:
    """Thread-safe JSON-backed session index."""

    def __init__(self, path: Path | None = None) -> None:
        base = default_sessions_dir() if path is None else path.parent
        self._path = path if path is not None else (base / "index.json")
        self._lock = _path_lock(self._path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def path(self) -> Path:
        """Return backing file path."""
        return self._path

    def list_sessions(self, include_archived: bool = False, include_lanes: bool = False) -> list[SessionIndexEntry]:
        """Return all sessions sorted by most recent update."""
        with self._lock:
            entries = list(self._load_map().values())
        if not include_archived:
            entries = [entry for entry in entries if not entry.archived]
        if not include_lanes:
            entries = [entry for entry in entries if entry.session_type not in {"fleet_lane", "forecast_lane"}]
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
        persona_id: str | None = None,
        persona_flavor_id: str | None = None,
        persona_privacy_tier: str | None = None,
        workspace_root: str | None = None,
        session_type: str = "standard",
        parent_session_key: str | None = None,
        participant_id: str | None = None,
    ) -> SessionIndexEntry:
        """Create a new locked session."""
        normalized_key = session_key.strip()
        normalized_provider = provider.strip()
        normalized_model = model.strip() if model else None
        normalized_title = title.strip() if title else None
        normalized_system_prompt_id = system_prompt_id.strip() if system_prompt_id else None
        normalized_task_prompt_id = task_prompt_id.strip() if task_prompt_id else None
        normalized_persona_id = persona_id.strip() if persona_id else None
        normalized_persona_flavor_id = persona_flavor_id.strip() if persona_flavor_id else None
        normalized_persona_privacy_tier = persona_privacy_tier.strip() if persona_privacy_tier else None
        normalized_workspace_root = workspace_root.strip() if workspace_root else None
        if not normalized_key:
            raise ValueError("session_key is required")
        if not _is_safe_store_key(normalized_key):
            raise ValueError(
                f"session_key contains characters unsafe for durable storage: {normalized_key!r} "
                "(allowed: letters, digits, '-', '_', '.')"
            )
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
                persona_id=normalized_persona_id,
                persona_flavor_id=normalized_persona_flavor_id,
                persona_privacy_tier=normalized_persona_privacy_tier,
                workspace_root=normalized_workspace_root,
                archived=False,
                provider_session_id=None,
                created_at=now,
                updated_at=now,
                last_run_id=None,
                in_flight_run_id=None,
                session_type=session_type.strip() or "standard",
                parent_session_key=parent_session_key.strip() if parent_session_key else None,
                participant_id=participant_id.strip() if participant_id else None,
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
        persona_id: str | None = None,
        persona_flavor_id: str | None = None,
        persona_privacy_tier: str | None = None,
        workspace_root: str | None = None,
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
            persona_id=persona_id,
            persona_flavor_id=persona_flavor_id,
            persona_privacy_tier=persona_privacy_tier,
            workspace_root=workspace_root,
        )

    def assert_session_binding(
        self,
        session_key: str,
        provider: str,
        model: str | None = None,
        system_prompt_id: str | None = None,
        task_prompt_id: str | None = None,
        persona_id: str | None = None,
        persona_flavor_id: str | None = None,
        persona_privacy_tier: str | None = None,
        workspace_root: str | None = None,
    ) -> SessionIndexEntry:
        """Enforce the session's locked binding, reconciling the mutable runtime fields.

        Mid-session runtime mutability (A + B1): **provider** stays hard-locked — a
        session's identity is per-provider, and cross-provider switching is a separate,
        larger change. **Profile / persona / workspace** stay soft-locked (only enforced
        when set at creation). But **model** (same provider) and **Access / task mode**
        are now mutable mid-session: when the request differs, the stored binding is
        reconciled to the new runtime so the session remembers its current setup. Every
        run is still stamped with the exact provider/model it used in the transcript and
        run record, so switching stays fully auditable per-turn. Full Access escalation
        remains gated downstream in ``policy_for_task_mode`` (provider gate), so a
        mid-session Access change can never silently over-grant.
        """
        normalized_key = session_key.strip()
        normalized_provider = provider.strip()
        normalized_model = model.strip() if model else None
        normalized_system_prompt_id = system_prompt_id.strip() if system_prompt_id else None
        normalized_task_prompt_id = task_prompt_id.strip() if task_prompt_id else None
        normalized_persona_id = persona_id.strip() if persona_id else None
        normalized_persona_flavor_id = persona_flavor_id.strip() if persona_flavor_id else None
        normalized_persona_privacy_tier = persona_privacy_tier.strip() if persona_privacy_tier else None
        normalized_workspace_root = workspace_root.strip() if workspace_root else None
        if not normalized_key:
            raise ValueError("session_key is required")

        with self._lock:
            sessions = self._load_map()
            entry = sessions.get(normalized_key)
            if entry is None:
                raise KeyError(f"unknown session_key: {normalized_key}")
            if entry.archived:
                raise RuntimeError(f"session is archived: {normalized_key}")
            # Provider is the one hard lock — identity is per-provider.
            if entry.provider != normalized_provider:
                raise RuntimeError(
                    f"session is locked to provider {entry.provider}; requested {normalized_provider}"
                )
            if entry.system_prompt_id and entry.system_prompt_id != normalized_system_prompt_id:
                raise RuntimeError(
                    f"session is locked to profile {entry.system_prompt_id}; requested {normalized_system_prompt_id or 'none'}"
                )
            if entry.persona_id and entry.persona_id != normalized_persona_id:
                raise RuntimeError(
                    f"session is locked to persona {entry.persona_id}; requested {normalized_persona_id or 'none'}"
                )
            if entry.persona_flavor_id and entry.persona_flavor_id != normalized_persona_flavor_id:
                raise RuntimeError(
                    f"session is locked to persona flavor {entry.persona_flavor_id}; requested {normalized_persona_flavor_id or 'none'}"
                )
            if entry.persona_privacy_tier and entry.persona_privacy_tier != normalized_persona_privacy_tier:
                raise RuntimeError(
                    f"session is locked to persona privacy tier {entry.persona_privacy_tier}; requested {normalized_persona_privacy_tier or 'none'}"
                )
            if entry.workspace_root and entry.workspace_root != normalized_workspace_root:
                raise RuntimeError(
                    f"session is locked to workspace root {entry.workspace_root}; requested {normalized_workspace_root or 'default'}"
                )

            # Reconcile the mutable runtime fields: switch the session's model (same
            # provider) and Access level to the requested values. A missing model in the
            # request never clears a stored model — only an explicit switch updates it.
            dirty = False
            if normalized_model and entry.model != normalized_model:
                entry.model = normalized_model
                dirty = True
            if _effective_task_mode(entry.task_prompt_id) != _effective_task_mode(normalized_task_prompt_id):
                entry.task_prompt_id = normalized_task_prompt_id
                dirty = True
            if dirty:
                entry.updated_at = utc_now_iso()
                sessions[normalized_key] = entry
                self._save_map(sessions)
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

    def clear_stale_in_flight(self) -> list[tuple[str, str, str, str | None]]:
        """Clear every persisted in_flight_run_id at process startup.

        A freshly started process owns no live runs, so any in_flight marker on
        disk is a leftover from a crash or kill mid-run. Without this sweep a
        stuck marker bricks the session forever: every future send raises
        "session is in flight" and abort can't help (it only consults in-memory
        state). Returns (session_key, run_id, provider, model) for each session
        that was stuck, so the caller can record synthetic 'interrupted' runs.
        """
        with self._lock:
            sessions = self._load_map()
            stuck: list[tuple[str, str, str, str | None]] = []
            for key, entry in sessions.items():
                if entry.in_flight_run_id:
                    stuck.append((key, entry.in_flight_run_id, entry.provider, entry.model))
                    entry.in_flight_run_id = None
                    entry.updated_at = utc_now_iso()
            if stuck:
                self._save_map(sessions)
            return stuck

    def _load_map(self) -> dict[str, SessionIndexEntry]:
        if not self._path.exists():
            return {}

        try:
            text = self._path.read_text(encoding="utf-8")
        except OSError as exc:
            raise SessionIndexError(f"could not read session index {self._path}: {exc}") from exc

        # An empty file is the benign "no sessions yet" case (e.g. a fresh touch).
        if not text.strip():
            return {}

        try:
            raw = json.loads(text)
        except json.JSONDecodeError as exc:
            # Preserve the corrupt bytes for forensics instead of letting the
            # next load->modify->save silently overwrite the real index.
            backup = self._path.with_suffix(self._path.suffix + ".corrupt")
            try:
                backup.write_text(text, encoding="utf-8")
            except OSError:
                backup = None  # best-effort; still fail loud below
            raise SessionIndexError(
                f"session index {self._path} is corrupt and was not parseable"
                + (f"; corrupt copy saved to {backup}" if backup else "")
            ) from exc

        items = raw.get("sessions") if isinstance(raw, dict) else None
        if not isinstance(items, list):
            raise SessionIndexError(
                f"session index {self._path} is malformed (missing 'sessions' list)"
            )

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
        # flush + fsync before the atomic rename so a power loss can't leave a
        # zero-length index behind (which _load_map would then refuse to parse).
        with open(tmp_path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
            fh.flush()
            os.fsync(fh.fileno())
        tmp_path.replace(self._path)
