"""Append-only transcript storage for CopeNet sessions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import threading
from typing import Any

from copenet._paths import default_sessions_dir


UTC = timezone.utc


def utc_now_iso() -> str:
    """Return current UTC timestamp in ISO-8601 format."""
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class TranscriptMessage:
    """Single transcript message record."""

    run_id: str
    role: str
    content: str
    provider: str
    model: str | None
    provider_session_id: str | None
    timestamp: str
    state: str | None = None
    tool_execution: dict[str, Any] | None = None
    parts: list[dict[str, Any]] | None = None
    # Image (and future file) attachment refs for a user turn: list of
    # {attachmentId, mimeType, filename}. Bytes live in ChatAttachmentStore; only
    # the refs are persisted here so replay can re-inline the images.
    attachments: list[dict[str, Any]] | None = None

    def to_json(self) -> dict[str, Any]:
        """Convert message into a JSON-serializable dictionary."""
        payload: dict[str, Any] = {
            "run_id": self.run_id,
            "role": self.role,
            "content": self.content,
            "provider": self.provider,
            "model": self.model,
            "provider_session_id": self.provider_session_id,
            "timestamp": self.timestamp,
        }
        if self.state:
            payload["state"] = self.state
        if self.tool_execution:
            payload["tool_execution"] = self.tool_execution
        if self.parts:
            payload["parts"] = [dict(part) for part in self.parts]
        if self.attachments:
            payload["attachments"] = [dict(ref) for ref in self.attachments]
        return payload


def to_public_message(record: dict[str, Any]) -> dict[str, Any]:
    """Convert one storage transcript record into the wire/public shape."""
    return {
        "runId": record.get("run_id"),
        "role": record.get("role"),
        "content": record.get("content"),
        "provider": record.get("provider"),
        "model": record.get("model"),
        "providerSessionId": record.get("provider_session_id"),
        "timestamp": record.get("timestamp"),
        "state": record.get("state"),
        "toolExecution": record.get("tool_execution"),
        "parts": record.get("parts") if isinstance(record.get("parts"), list) else None,
        "attachments": record.get("attachments") if isinstance(record.get("attachments"), list) else None,
    }


class TranscriptStore:
    """File-backed append-only JSONL transcript store."""

    def __init__(self, root_dir: Path | None = None) -> None:
        self._root_dir = root_dir if root_dir is not None else default_sessions_dir()
        self._root_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def transcript_path_for(self, session_id: str) -> Path:
        """Resolve transcript path for a session id."""
        safe = "".join(ch for ch in session_id if ch.isalnum() or ch in ("-", "_", ".")).strip()
        if not safe:
            raise ValueError("invalid session_id")
        return self._root_dir / f"{safe}.jsonl"

    def append_message(self, session_id: str, message: TranscriptMessage) -> None:
        """Append one message record to the transcript."""
        path = self.transcript_path_for(session_id)
        line = json.dumps(message.to_json(), ensure_ascii=False)
        with self._lock:
            with path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(line + "\n")
                handle.flush()
                os.fsync(handle.fileno())

    def read_history(self, session_id: str, limit: int = 200) -> list[dict[str, Any]]:
        """Read bounded transcript history for a session."""
        path = self.transcript_path_for(session_id)
        if not path.exists():
            return []
        if limit <= 0:
            return []

        with self._lock:
            lines = path.read_text(encoding="utf-8").splitlines()

        records: list[dict[str, Any]] = []
        for line in lines[-limit:]:
            line = line.strip()
            if not line:
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                records.append(parsed)
        return records

    def copy_history(self, source_session_id: str, target_session_id: str) -> int:
        """Copy all transcript records from one session id to another."""
        records = self.read_history(source_session_id, limit=100000)
        count = 0
        for record in records:
            self.append_message(
                target_session_id,
                TranscriptMessage(
                    run_id=str(record.get("run_id") or ""),
                    role=str(record.get("role") or "assistant"),
                    content=str(record.get("content") or ""),
                    provider=str(record.get("provider") or ""),
                    model=str(record.get("model")) if record.get("model") is not None else None,
                    provider_session_id=str(record.get("provider_session_id")) if record.get("provider_session_id") is not None else None,
                    timestamp=str(record.get("timestamp") or utc_now_iso()),
                    state=str(record.get("state")) if record.get("state") is not None else None,
                    tool_execution=dict(record.get("tool_execution")) if isinstance(record.get("tool_execution"), dict) else None,
                    parts=[dict(part) for part in record.get("parts")] if isinstance(record.get("parts"), list) else None,
                    attachments=[dict(ref) for ref in record.get("attachments")] if isinstance(record.get("attachments"), list) else None,
                ),
            )
            count += 1
        return count
