"""Persistent media asset records for CopeNet."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import threading
from typing import Any
from uuid import uuid4

from copenet._paths import default_media_dir


UTC = timezone.utc


def utc_now_iso() -> str:
    """Return current UTC time as ISO-8601."""
    return datetime.now(UTC).isoformat()


def slugify_filename(value: str, *, fallback: str = "media") -> str:
    """Return a filesystem-safe slug."""
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "-", (value or "").strip())
    cleaned = cleaned.strip(".-")
    return cleaned[:80] or fallback


@dataclass(frozen=True)
class MediaAssetRecord:
    """Stored representation of one imported media asset."""

    asset_id: str
    app_id: str
    source_type: str
    source_url: str | None
    source_path: str | None
    title: str
    media_path: str | None
    transcript_path: str | None
    transcript_source: str | None
    transcript_excerpt: str
    metadata: dict[str, Any] = field(default_factory=dict)
    duration_seconds: float | None = None
    latency_ms: int | None = None
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    def to_public_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly public payload."""
        return {
            "assetId": self.asset_id,
            "appId": self.app_id,
            "sourceType": self.source_type,
            "sourceUrl": self.source_url,
            "sourcePath": self.source_path,
            "title": self.title,
            "mediaPath": self.media_path,
            "transcriptPath": self.transcript_path,
            "transcriptSource": self.transcript_source,
            "transcriptExcerpt": self.transcript_excerpt,
            "metadata": self.metadata,
            "durationSeconds": self.duration_seconds,
            "latencyMs": self.latency_ms,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
        }


class MediaAssetStore:
    """File-backed storage for imported media assets."""

    def __init__(self, root_dir: Path | None = None) -> None:
        self._root_dir = (root_dir or default_media_dir()).resolve()
        self.downloads_dir = self._root_dir / "downloads"
        self.transcripts_dir = self._root_dir / "transcripts"
        self.records_dir = self._root_dir / "records"
        for path in (self._root_dir, self.downloads_dir, self.transcripts_dir, self.records_dir):
            path.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def next_asset_id(self) -> str:
        """Return a new asset id."""
        return f"media-{uuid4().hex[:12]}"

    def record_path_for(self, asset_id: str) -> Path:
        """Resolve the JSON path for an asset id."""
        safe = slugify_filename(asset_id, fallback="media")
        return self.records_dir / f"{safe}.json"

    def save_transcript(self, *, asset_id: str, title: str, transcript: str) -> Path:
        """Persist transcript text for an asset."""
        safe_title = slugify_filename(title, fallback=asset_id)
        path = self.transcripts_dir / f"{safe_title}-{asset_id}.md"
        with self._lock:
            path.write_text(transcript, encoding="utf-8")
        return path

    def save_record(self, record: MediaAssetRecord) -> MediaAssetRecord:
        """Persist a record JSON file."""
        path = self.record_path_for(record.asset_id)
        payload = asdict(record)
        tmp = path.with_suffix(".json.tmp")
        with self._lock:
            tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(path)
        return record

    def get_record(self, asset_id: str) -> MediaAssetRecord | None:
        """Load one asset record by id."""
        path = self.record_path_for(asset_id)
        if not path.exists():
            return None
        with self._lock:
            try:
                parsed = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return None
        if not isinstance(parsed, dict):
            return None
        try:
            return MediaAssetRecord(**parsed)
        except TypeError:
            return None

    def read_transcript(self, record: MediaAssetRecord) -> str:
        """Read full transcript text for a stored asset."""
        if not record.transcript_path:
            return ""
        path = Path(record.transcript_path)
        if not path.is_file():
            return ""
        with self._lock:
            try:
                return path.read_text(encoding="utf-8")
            except OSError:
                return ""

    def list_records(self, *, app_id: str | None = None, limit: int = 50) -> list[MediaAssetRecord]:
        """List newest stored records, optionally filtered by app id."""
        if limit <= 0:
            return []
        records: list[MediaAssetRecord] = []
        with self._lock:
            candidates = sorted(self.records_dir.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
            for path in candidates:
                try:
                    parsed = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                if not isinstance(parsed, dict):
                    continue
                if app_id and parsed.get("app_id") != app_id:
                    continue
                try:
                    records.append(MediaAssetRecord(**parsed))
                except TypeError:
                    continue
                if len(records) >= limit:
                    break
        return records
