"""Minimal runtime artifact storage."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
import threading
from typing import Any
from uuid import uuid4

from copenet._paths import default_artifacts_dir
from copenet.core.sessions.session_store import utc_now_iso


def _safe_name(value: str) -> str:
    return "".join(ch for ch in value if ch.isalnum() or ch in ("-", "_", ".")).strip()


@dataclass
class ArtifactRecord:
    """One durable derived runtime output."""

    artifact_id: str
    session_key: str
    run_id: str
    type: str
    title: str
    body: str
    source_asset_ids: list[str] = field(default_factory=list)
    source_artifact_ids: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_json(cls, raw: dict[str, Any]) -> "ArtifactRecord":
        """Normalize one stored artifact payload."""
        return cls(
            artifact_id=str(raw.get("artifact_id") or "").strip(),
            session_key=str(raw.get("session_key") or "").strip(),
            run_id=str(raw.get("run_id") or "").strip(),
            type=str(raw.get("type") or "").strip(),
            title=str(raw.get("title") or "").strip(),
            body=str(raw.get("body") or ""),
            source_asset_ids=_string_list(raw.get("source_asset_ids")),
            source_artifact_ids=_string_list(raw.get("source_artifact_ids")),
            created_at=str(raw.get("created_at") or utc_now_iso()),
            updated_at=str(raw.get("updated_at") or utc_now_iso()),
            metadata=dict(raw.get("metadata") or {}) if isinstance(raw.get("metadata"), dict) else {},
        )

    def to_json(self) -> dict[str, Any]:
        """Return a JSON-serializable payload."""
        return asdict(self)

    def to_public_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly payload for RPC clients."""
        return {
            "artifactId": self.artifact_id,
            "sessionKey": self.session_key,
            "runId": self.run_id,
            "type": self.type,
            "title": self.title,
            "body": self.body,
            "sourceAssetIds": list(self.source_asset_ids),
            "sourceArtifactIds": list(self.source_artifact_ids),
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
            "metadata": dict(self.metadata),
        }


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    rows: list[str] = []
    for item in value:
        text = str(item).strip()
        if text:
            rows.append(text)
    return rows


class ArtifactStore:
    """Append-only session-scoped artifact store."""

    def __init__(self, root_dir: Path | None = None) -> None:
        self._root_dir = root_dir if root_dir is not None else default_artifacts_dir()
        self._root_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def artifacts_path_for(self, session_key: str) -> Path:
        """Resolve artifact ledger path for one session key."""
        safe = _safe_name(session_key)
        if not safe:
            raise ValueError("invalid session_key")
        return self._root_dir / f"{safe}.jsonl"

    def create(
        self,
        *,
        session_key: str,
        run_id: str,
        artifact_type: str,
        title: str,
        body: str,
        source_asset_ids: list[str] | None = None,
        source_artifact_ids: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ArtifactRecord:
        """Append one new artifact record."""
        now = utc_now_iso()
        record = ArtifactRecord(
            artifact_id=str(uuid4()),
            session_key=session_key.strip(),
            run_id=run_id.strip(),
            type=artifact_type.strip(),
            title=title.strip(),
            body=body,
            source_asset_ids=list(source_asset_ids or []),
            source_artifact_ids=list(source_artifact_ids or []),
            created_at=now,
            updated_at=now,
            metadata=dict(metadata or {}),
        )
        path = self.artifacts_path_for(record.session_key)
        line = json.dumps(record.to_json(), ensure_ascii=False)
        with self._lock:
            with path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(line + "\n")
        return record

    def list_for_session(self, session_key: str, limit: int = 50) -> list[ArtifactRecord]:
        """Return recent artifacts for one session."""
        path = self.artifacts_path_for(session_key)
        if not path.exists() or limit <= 0:
            return []
        with self._lock:
            lines = path.read_text(encoding="utf-8").splitlines()
        rows: list[ArtifactRecord] = []
        for line in lines[-limit:]:
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(raw, dict):
                rows.append(ArtifactRecord.from_json(raw))
        return rows

    def get(self, session_key: str, artifact_id: str) -> ArtifactRecord | None:
        """Return one artifact by id."""
        for record in reversed(self.list_for_session(session_key, limit=500)):
            if record.artifact_id == artifact_id:
                return record
        return None
