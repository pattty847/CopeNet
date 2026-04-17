"""Durable run records for stateful CopeNet execution."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
import threading
from typing import Any

from copenet.core.runtime.artifacts import _safe_name
from copenet.core.sessions.session_store import utc_now_iso


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    rows: list[str] = []
    for item in value:
        text = str(item).strip()
        if text:
            rows.append(text)
    return rows


def _step_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    rows: list[dict[str, Any]] = []
    for item in value:
        if isinstance(item, dict):
            rows.append(dict(item))
    return rows


def _dict_value(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


@dataclass
class RunRecord:
    """One durable summary of a completed or failed run."""

    run_id: str
    session_key: str
    provider: str
    model: str | None
    status: str
    user_message: str
    tool_execution_mode: str
    will_attempt_tool_loop: bool
    started_at: str = field(default_factory=utc_now_iso)
    completed_at: str | None = None
    working_set: dict[str, Any] = field(default_factory=dict)
    tool_steps: list[dict[str, Any]] = field(default_factory=list)
    artifact_ids: list[str] = field(default_factory=list)
    output_summary: str = ""
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_json(cls, raw: dict[str, Any]) -> "RunRecord":
        """Normalize one stored run payload."""
        return cls(
            run_id=str(raw.get("run_id") or "").strip(),
            session_key=str(raw.get("session_key") or "").strip(),
            provider=str(raw.get("provider") or "").strip(),
            model=str(raw.get("model")).strip() if raw.get("model") is not None else None,
            status=str(raw.get("status") or "").strip(),
            user_message=str(raw.get("user_message") or ""),
            tool_execution_mode=str(raw.get("tool_execution_mode") or "none").strip(),
            will_attempt_tool_loop=bool(raw.get("will_attempt_tool_loop")),
            started_at=str(raw.get("started_at") or utc_now_iso()),
            completed_at=str(raw.get("completed_at")).strip() if raw.get("completed_at") is not None else None,
            working_set=_dict_value(raw.get("working_set")),
            tool_steps=_step_list(raw.get("tool_steps")),
            artifact_ids=_string_list(raw.get("artifact_ids")),
            output_summary=str(raw.get("output_summary") or ""),
            error=str(raw.get("error")).strip() if raw.get("error") is not None else None,
            metadata=_dict_value(raw.get("metadata")),
        )

    def to_json(self) -> dict[str, Any]:
        """Return a JSON-serializable payload."""
        return asdict(self)

    def to_public_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly payload for RPC clients."""
        return {
            "runId": self.run_id,
            "sessionKey": self.session_key,
            "provider": self.provider,
            "model": self.model,
            "status": self.status,
            "userMessage": self.user_message,
            "toolExecutionMode": self.tool_execution_mode,
            "willAttemptToolLoop": self.will_attempt_tool_loop,
            "startedAt": self.started_at,
            "completedAt": self.completed_at,
            "workingSet": dict(self.working_set),
            "toolSteps": [dict(step) for step in self.tool_steps],
            "artifactIds": list(self.artifact_ids),
            "outputSummary": self.output_summary,
            "error": self.error,
            "metadata": dict(self.metadata),
        }


class RunStore:
    """Append-only session-scoped run record store."""

    def __init__(self, root_dir: Path) -> None:
        self._root_dir = root_dir
        self._root_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def runs_path_for(self, session_key: str) -> Path:
        safe = _safe_name(session_key)
        if not safe:
            raise ValueError("invalid session_key")
        return self._root_dir / f"{safe}.jsonl"

    def create(self, record: RunRecord) -> RunRecord:
        """Append one run record."""
        path = self.runs_path_for(record.session_key)
        line = json.dumps(record.to_json(), ensure_ascii=False)
        with self._lock:
            with path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(line + "\n")
        return record

    def list_for_session(self, session_key: str, limit: int = 50) -> list[RunRecord]:
        """Return recent run records for one session."""
        path = self.runs_path_for(session_key)
        if not path.exists() or limit <= 0:
            return []
        with self._lock:
            lines = path.read_text(encoding="utf-8").splitlines()
        rows: list[RunRecord] = []
        for line in lines[-limit:]:
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(raw, dict):
                rows.append(RunRecord.from_json(raw))
        return rows

    def get(self, session_key: str, run_id: str) -> RunRecord | None:
        """Return one run record by id."""
        for record in reversed(self.list_for_session(session_key, limit=500)):
            if record.run_id == run_id:
                return record
        return None
