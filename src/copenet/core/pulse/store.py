"""Durable local-first Pulse storage for operator follow-up opportunities."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import threading
from typing import Any, Literal

from copenet.core.sessions.session_store import utc_now_iso

PulseStatus = Literal["new", "saved", "dismissed"]


@dataclass(frozen=True)
class PulseRecord:
    pulse_id: str
    status: PulseStatus
    title: str
    summary: str
    why_now: str
    source_session_keys: list[str]
    source_run_ids: list[str]
    created_at: str
    updated_at: str
    saved_at: str | None = None
    dismissed_at: str | None = None

    @classmethod
    def from_json(cls, raw: dict[str, Any]) -> "PulseRecord":
        now = utc_now_iso()
        return cls(
            pulse_id=_required_text(raw, "pulse_id"),
            status=_pulse_status(raw.get("status")),
            title=_required_text(raw, "title"),
            summary=_required_text(raw, "summary"),
            why_now=_required_text(raw, "why_now"),
            source_session_keys=_string_list(raw.get("source_session_keys")),
            source_run_ids=_string_list(raw.get("source_run_ids")),
            created_at=_required_text(raw, "created_at") or now,
            updated_at=_required_text(raw, "updated_at") or now,
            saved_at=_optional_text(raw, "saved_at"),
            dismissed_at=_optional_text(raw, "dismissed_at"),
        )

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


class PulseStore:
    """Thread-safe JSON store for Pulse records."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def list(self, *, status: PulseStatus | None = None) -> list[PulseRecord]:
        with self._lock:
            rows = self._load_payload()
        records = list(rows.values())
        records.sort(key=lambda item: item.updated_at, reverse=True)
        if status is not None:
            records = [item for item in records if item.status == status]
        return records

    def get(self, pulse_id: str) -> PulseRecord | None:
        with self._lock:
            return self._load_payload().get(pulse_id.strip())

    def create(self, record: PulseRecord) -> PulseRecord:
        if not record.pulse_id:
            raise ValueError("pulse_id is required")
        if not record.source_session_keys:
            raise ValueError("source_session_keys is required")
        with self._lock:
            payload = self._load_payload()
            if record.pulse_id in payload:
                raise ValueError(f"pulse already exists: {record.pulse_id}")
            persisted = _refresh_record(record)
            payload[persisted.pulse_id] = persisted
            self._save_payload(payload)
        return persisted

    def save(self, record: PulseRecord) -> PulseRecord:
        if not record.pulse_id:
            raise ValueError("pulse_id is required")
        if not record.source_session_keys:
            raise ValueError("source_session_keys is required")
        with self._lock:
            payload = self._load_payload()
            persisted = _refresh_record(record)
            payload[persisted.pulse_id] = persisted
            self._save_payload(payload)
        return persisted

    def _load_payload(self) -> dict[str, PulseRecord]:
        if not self._path.exists():
            return {}
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        rows = raw.get("pulses") if isinstance(raw, dict) else None
        records: dict[str, PulseRecord] = {}
        if isinstance(rows, list):
            for item in rows:
                if not isinstance(item, dict):
                    continue
                record = PulseRecord.from_json(item)
                if record.pulse_id:
                    records[record.pulse_id] = record
        return records

    def _save_payload(self, payload: dict[str, PulseRecord]) -> None:
        serialized = {
            "pulses": [record.to_json() for record in sorted(payload.values(), key=lambda item: item.updated_at, reverse=True)]
        }
        tmp_path = self._path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(serialized, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_path.replace(self._path)


def _required_text(raw: dict[str, Any], key: str) -> str:
    value = raw.get(key)
    return str(value).strip() if value is not None else ""


def _optional_text(raw: dict[str, Any], key: str) -> str | None:
    value = raw.get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _string_list(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    rows: list[str] = []
    for item in raw:
        text = str(item or "").strip()
        if text:
            rows.append(text)
    return rows


def _pulse_status(value: Any) -> PulseStatus:
    text = str(value or "new").strip().lower()
    if text in {"saved", "dismissed"}:
        return text
    return "new"


def _refresh_record(record: PulseRecord) -> PulseRecord:
    return PulseRecord(
        pulse_id=record.pulse_id,
        status=record.status,
        title=record.title.strip(),
        summary=record.summary.strip(),
        why_now=record.why_now.strip(),
        source_session_keys=[item for item in record.source_session_keys if str(item).strip()],
        source_run_ids=[item for item in record.source_run_ids if str(item).strip()],
        created_at=record.created_at or utc_now_iso(),
        updated_at=utc_now_iso(),
        saved_at=record.saved_at,
        dismissed_at=record.dismissed_at,
    )
