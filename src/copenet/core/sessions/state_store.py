"""Structured session state storage for CopeNet runtime state."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
import threading
from typing import Any

from copenet._paths import default_session_state_dir
from copenet.core.sessions.session_store import utc_now_iso


def _safe_name(value: str) -> str:
    return "".join(ch for ch in value if ch.isalnum() or ch in ("-", "_", ".")).strip()


@dataclass
class SessionStateRecord:
    """Curated session runtime state persisted outside the transcript log."""

    session_key: str
    task_summary: str | None = None
    goals: list[str] = field(default_factory=list)
    active_entities: list[str] = field(default_factory=list)
    working_set_refs: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    unresolved_questions: list[str] = field(default_factory=list)
    prior_decisions: list[str] = field(default_factory=list)
    starter_intent: str | None = None
    topical_tags: list[str] = field(default_factory=list)
    plan_snapshot: dict[str, Any] = field(default_factory=dict)
    relevant_asset_ids: list[str] = field(default_factory=list)
    relevant_artifact_ids: list[str] = field(default_factory=list)
    merge_state: dict[str, Any] = field(default_factory=dict)
    pulse_state: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    @classmethod
    def from_json(cls, raw: dict[str, Any]) -> "SessionStateRecord":
        """Normalize one stored session state payload."""
        return cls(
            session_key=str(raw.get("session_key") or "").strip(),
            task_summary=_optional_text(raw.get("task_summary")),
            goals=_string_list(raw.get("goals")),
            active_entities=_string_list(raw.get("active_entities")),
            working_set_refs=_string_list(raw.get("working_set_refs")),
            constraints=_string_list(raw.get("constraints")),
            unresolved_questions=_string_list(raw.get("unresolved_questions")),
            prior_decisions=_string_list(raw.get("prior_decisions")),
            starter_intent=_optional_text(raw.get("starter_intent")),
            topical_tags=_string_list(raw.get("topical_tags")),
            plan_snapshot=_dict_value(raw.get("plan_snapshot")),
            relevant_asset_ids=_string_list(raw.get("relevant_asset_ids")),
            relevant_artifact_ids=_string_list(raw.get("relevant_artifact_ids")),
            merge_state=_dict_value(raw.get("merge_state")),
            pulse_state=_dict_value(raw.get("pulse_state")),
            created_at=str(raw.get("created_at") or utc_now_iso()),
            updated_at=str(raw.get("updated_at") or utc_now_iso()),
        )

    def to_json(self) -> dict[str, Any]:
        """Return a JSON-serializable payload."""
        return asdict(self)


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    rows: list[str] = []
    for item in value:
        text = str(item).strip()
        if text:
            rows.append(text)
    return rows


def _dict_value(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


class SessionStateStore:
    """File-backed session state storage keyed by session key."""

    def __init__(self, root_dir: Path | None = None) -> None:
        self._root_dir = root_dir if root_dir is not None else default_session_state_dir()
        self._root_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def state_path_for(self, session_key: str) -> Path:
        """Resolve the state file path for one session key."""
        safe = _safe_name(session_key)
        if not safe:
            raise ValueError("invalid session_key")
        return self._root_dir / f"{safe}.json"

    def get(self, session_key: str) -> SessionStateRecord | None:
        """Read one session state record if present."""
        path = self.state_path_for(session_key)
        if not path.exists():
            return None
        with self._lock:
            raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return None
        record = SessionStateRecord.from_json(raw)
        return record if record.session_key else None

    def get_or_create(self, session_key: str) -> SessionStateRecord:
        """Load an existing state record or create a default one."""
        existing = self.get(session_key)
        if existing is not None:
            return existing
        created = SessionStateRecord(session_key=session_key.strip())
        self.save(created)
        return created

    def save(self, record: SessionStateRecord) -> SessionStateRecord:
        """Persist one full session state record atomically."""
        path = self.state_path_for(record.session_key)
        payload = record.to_json()
        payload["updated_at"] = utc_now_iso()
        tmp_path = path.with_suffix(".tmp")
        with self._lock:
            tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp_path.replace(path)
        return SessionStateRecord.from_json(payload)
