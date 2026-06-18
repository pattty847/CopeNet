"""Durable local-first storage for NASA Astronomy Picture of the Day records.

The collection is keyed by APOD date (one image per day), append-only in spirit:
re-fetching a date refreshes its fields but never drops earlier days.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import threading
from typing import Any

from copenet.core.sessions.session_store import utc_now_iso


@dataclass(frozen=True)
class NasaApodRecord:
    date: str  # YYYY-MM-DD, primary key (one APOD per day)
    title: str
    explanation: str
    url: str
    media_type: str  # "image" | "video"
    hdurl: str | None = None
    thumbnail_url: str | None = None
    copyright: str | None = None
    service_version: str | None = None
    created_at: str = ""
    updated_at: str = ""

    @classmethod
    def from_json(cls, raw: dict[str, Any]) -> "NasaApodRecord":
        now = utc_now_iso()
        return cls(
            date=_required_text(raw, "date"),
            title=_required_text(raw, "title"),
            explanation=_required_text(raw, "explanation"),
            url=_required_text(raw, "url"),
            media_type=_media_type(raw.get("media_type")),
            hdurl=_optional_text(raw, "hdurl"),
            thumbnail_url=_optional_text(raw, "thumbnail_url"),
            copyright=_optional_text(raw, "copyright"),
            service_version=_optional_text(raw, "service_version"),
            created_at=_required_text(raw, "created_at") or now,
            updated_at=_required_text(raw, "updated_at") or now,
        )

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


class NasaApodStore:
    """Thread-safe JSON store for collected APOD records."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def list(self, *, limit: int | None = None) -> list[NasaApodRecord]:
        with self._lock:
            rows = self._load_payload()
        records = list(rows.values())
        records.sort(key=lambda item: item.date, reverse=True)
        if limit is not None and limit >= 0:
            records = records[:limit]
        return records

    def get(self, date: str) -> NasaApodRecord | None:
        with self._lock:
            return self._load_payload().get(date.strip())

    def save(self, record: NasaApodRecord) -> NasaApodRecord:
        if not record.date:
            raise ValueError("date is required")
        with self._lock:
            payload = self._load_payload()
            existing = payload.get(record.date)
            persisted = _refresh_record(record, existing=existing)
            payload[persisted.date] = persisted
            self._save_payload(payload)
        return persisted

    def _load_payload(self) -> dict[str, NasaApodRecord]:
        if not self._path.exists():
            return {}
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        rows = raw.get("apods") if isinstance(raw, dict) else None
        records: dict[str, NasaApodRecord] = {}
        if isinstance(rows, list):
            for item in rows:
                if not isinstance(item, dict):
                    continue
                record = NasaApodRecord.from_json(item)
                if record.date:
                    records[record.date] = record
        return records

    def _save_payload(self, payload: dict[str, NasaApodRecord]) -> None:
        serialized = {
            "apods": [record.to_json() for record in sorted(payload.values(), key=lambda item: item.date, reverse=True)]
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


def _media_type(value: Any) -> str:
    text = str(value or "image").strip().lower()
    return text if text in {"image", "video"} else "image"


def _refresh_record(record: NasaApodRecord, *, existing: NasaApodRecord | None) -> NasaApodRecord:
    created_at = (existing.created_at if existing else "") or record.created_at or utc_now_iso()
    return NasaApodRecord(
        date=record.date.strip(),
        title=record.title.strip(),
        explanation=record.explanation.strip(),
        url=record.url.strip(),
        media_type=_media_type(record.media_type),
        hdurl=record.hdurl,
        thumbnail_url=record.thumbnail_url,
        copyright=record.copyright,
        service_version=record.service_version,
        created_at=created_at,
        updated_at=utc_now_iso(),
    )
