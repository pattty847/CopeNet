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

    def to_json(self) -> dict[str, Any]:
        """Convert message into a JSON-serializable dictionary."""
        payload: dict[str, Any] = {
            "runId": self.run_id,
            "role": self.role,
            "content": self.content,
            "provider": self.provider,
            "model": self.model,
            "providerSessionId": self.provider_session_id,
            "timestamp": self.timestamp,
        }
        if self.state:
            payload["state"] = self.state
        return payload


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
