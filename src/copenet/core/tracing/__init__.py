"""Structured per-run tracing for CopeNet.

Two tiers share one JSONL file per run:

- **lifecycle** (`record`) — always written. Run/session identity, resolved
  provider and model, the harness plan, tool requested/executed/blocked with
  tool id and status, token estimates, trim events, terminal reason, timings.
  This is what makes a run auditable after the fact, so it is not behind a
  setting. It carries no prompt text, no message history, no reasoning content,
  and no tool result bodies.
- **debug** (`record_debug`) — only while Debug capture is on. The model input
  snapshot, effective instructions, reasoning content, and tool result bodies.
  Large, and able to contain operator or repository data, so it stays opt-in.

Every row is stamped with its `tier` so a reader can tell the two apart without
knowing the event vocabulary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
import threading
from typing import Any

from copenet._paths import default_run_logs_dir


UTC = timezone.utc

TIER_LIFECYCLE = "lifecycle"
TIER_DEBUG = "debug"

# Events that are payload-heavy by nature and always belong to the debug tier,
# no matter which entry point emits them. The harness tool loops are handed a
# single `trace` callable rather than the writer, so without this table they
# could only reach the lifecycle tier. Keep it small and explicit: an event
# belongs here when its payload is the model's or the operator's content
# (prompt text, reasoning, tool arguments, tool result bodies) rather than
# metadata about what happened.
DEBUG_TIER_EVENTS = frozenset(
    {
        "run_input",
        "tool_arguments",
        "tool_result_body",
    }
)

# One pathological run (a tool loop echoing large bodies under Debug capture)
# must not be able to fill the disk. Past the cap the writer emits a single
# `trace_truncated` row and goes quiet for the rest of the run.
DEFAULT_MAX_BYTES_PER_RUN = 8 * 1024 * 1024


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
    debug: bool = False
    root_dir: Path | None = None
    max_bytes: int = DEFAULT_MAX_BYTES_PER_RUN
    _lock: threading.RLock = field(default_factory=threading.RLock, init=False, repr=False)
    _path: Path | None = field(default=None, init=False, repr=False)
    _written_bytes: int = field(default=0, init=False, repr=False)
    _truncated: bool = field(default=False, init=False, repr=False)

    @property
    def path(self) -> Path:
        """Return the path for this run trace file."""
        if self._path is None:
            root = self.root_dir if self.root_dir is not None else default_run_logs_dir()
            safe_run_id = "".join(ch for ch in self.run_id if ch.isalnum() or ch in ("-", "_", ".")).strip()
            self._path = root / f"{safe_run_id or 'run'}.jsonl"
        return self._path

    def record(self, event: str, payload: dict[str, Any] | None = None) -> None:
        """Append one trace event, routing DEBUG_TIER_EVENTS to the debug tier.

        Always on for lifecycle events; fails closed on write errors.
        """
        if event in DEBUG_TIER_EVENTS:
            self.record_debug(event, payload)
            return
        self._write(event, payload, tier=TIER_LIFECYCLE)

    def record_debug(self, event: str, payload: dict[str, Any] | None = None) -> None:
        """Append a sanitized high-detail event only while Debug capture is active."""
        if not self.debug:
            return
        self._write(event, _sanitize(payload or {}), tier=TIER_DEBUG)

    def _write(self, event: str, payload: dict[str, Any] | None, *, tier: str) -> None:
        if not self.enabled or self._truncated:
            return
        try:
            path = self.path
            path.parent.mkdir(parents=True, exist_ok=True)
            row: dict[str, Any] = {
                "timestamp": utc_now_iso(),
                "event": event,
                "tier": tier,
                "runId": self.run_id,
                "sessionKey": self.session_key,
                "provider": self.provider,
                "model": self.model,
            }
            if payload:
                row["payload"] = payload
            line = json.dumps(row, ensure_ascii=False) + "\n"
            encoded = line.encode("utf-8")
            with self._lock:
                if self.max_bytes > 0 and self._written_bytes + len(encoded) > self.max_bytes:
                    self._truncated = True
                    encoded = (
                        json.dumps(
                            {
                                "timestamp": utc_now_iso(),
                                "event": "trace_truncated",
                                "tier": TIER_LIFECYCLE,
                                "runId": self.run_id,
                                "sessionKey": self.session_key,
                                "provider": self.provider,
                                "model": self.model,
                                "payload": {"maxBytes": self.max_bytes, "droppedAtEvent": event},
                            },
                            ensure_ascii=False,
                        )
                        + "\n"
                    ).encode("utf-8")
                with path.open("ab") as handle:
                    handle.write(encoded)
                self._written_bytes += len(encoded)
        except Exception:
            return


_SECRET_KEYS = {
    "authorization",
    "cookie",
    "password",
    "secret",
    "token",
    "apikey",
    "accesstoken",
    "refreshtoken",
    "idtoken",
}


def _sanitize(value: Any) -> Any:
    """Redact credential-shaped fields before a debug payload reaches disk."""
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            normalized = str(key).lower().replace("-", "_")
            compact = normalized.replace("_", "")
            is_secret = compact in _SECRET_KEYS or "password" in compact or "secret" in compact
            sanitized[str(key)] = "[redacted]" if is_secret else _sanitize(item)
        return sanitized
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize(item) for item in value]
    return value
