"""Structured per-run tracing for CopeNet."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
import threading
from typing import Any

from copenet._paths import default_run_logs_dir


UTC = timezone.utc


def utc_now_iso() -> str:
    """Return current UTC timestamp in ISO-8601 format."""
    return datetime.now(UTC).isoformat()


@dataclass
class RunTraceWriter:
    """Append-only JSONL trace writer for one run."""

    run_id: str
    session_key: str
    provider: str
    model: str | None
    enabled: bool = False
    root_dir: Path | None = None
    _lock: threading.RLock = field(default_factory=threading.RLock, init=False, repr=False)
    _path: Path | None = field(default=None, init=False, repr=False)

    @property
    def path(self) -> Path:
        """Return the path for this run trace file."""
        if self._path is None:
            root = self.root_dir if self.root_dir is not None else default_run_logs_dir()
            safe_run_id = "".join(ch for ch in self.run_id if ch.isalnum() or ch in ("-", "_", ".")).strip()
            self._path = root / f"{safe_run_id or 'run'}.jsonl"
        return self._path

    def record(self, event: str, payload: dict[str, Any] | None = None) -> None:
        """Append one structured trace event. Fail closed if tracing is disabled or writing fails."""
        if not self.enabled:
            return
        try:
            path = self.path
            path.parent.mkdir(parents=True, exist_ok=True)
            row: dict[str, Any] = {
                "timestamp": utc_now_iso(),
                "event": event,
                "runId": self.run_id,
                "sessionKey": self.session_key,
                "provider": self.provider,
                "model": self.model,
            }
            if payload:
                row["payload"] = payload
            line = json.dumps(row, ensure_ascii=False)
            with self._lock:
                with path.open("a", encoding="utf-8", newline="\n") as handle:
                    handle.write(line + "\n")
        except Exception:
            return
