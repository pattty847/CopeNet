"""Durable run records for stateful CopeNet execution."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
from typing import Any

from copenet.core._json_store import _path_lock, append_jsonl
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
    # working_set is retained on the wire (emitted empty) until the Phase 4
    # frontend cleanup removes the consumer. message_count / input_token_estimate
    # replace its inspector value (Phase 1, HARNESS_REBUILD_V2 §1.4).
    working_set: dict[str, Any] = field(default_factory=dict)
    message_count: int = 0
    input_token_estimate: int = 0
    tool_steps: list[dict[str, Any]] = field(default_factory=list)
    artifact_ids: list[str] = field(default_factory=list)
    output_summary: str = ""
    error: str | None = None
    transition_reason: str = "start_turn"
    terminal_reason: str | None = None
    tool_results: list[dict[str, Any]] = field(default_factory=list)
    pending_input_count: int = 0
    oversized_tool_artifact_ids: list[str] = field(default_factory=list)
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
            message_count=int(raw.get("message_count") or 0),
            input_token_estimate=int(raw.get("input_token_estimate") or 0),
            tool_steps=_step_list(raw.get("tool_steps")),
            artifact_ids=_string_list(raw.get("artifact_ids")),
            output_summary=str(raw.get("output_summary") or ""),
            error=str(raw.get("error")).strip() if raw.get("error") is not None else None,
            transition_reason=str(raw.get("transition_reason") or "start_turn").strip(),
            terminal_reason=str(raw.get("terminal_reason")).strip() if raw.get("terminal_reason") is not None else None,
            tool_results=_step_list(raw.get("tool_results")),
            pending_input_count=int(raw.get("pending_input_count") or 0),
            oversized_tool_artifact_ids=_string_list(raw.get("oversized_tool_artifact_ids")),
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
            "messageCount": self.message_count,
            "inputTokenEstimate": self.input_token_estimate,
            "toolSteps": [dict(step) for step in self.tool_steps],
            "artifactIds": list(self.artifact_ids),
            "outputSummary": self.output_summary,
            "error": self.error,
            "transitionReason": self.transition_reason,
            "terminalReason": self.terminal_reason,
            "toolResults": [dict(item) for item in self.tool_results],
            "pendingInputCount": self.pending_input_count,
            "oversizedToolArtifactIds": list(self.oversized_tool_artifact_ids),
            "metadata": dict(self.metadata),
        }


class RunStore:
    """Append-only session-scoped run record store."""

    def __init__(self, root_dir: Path) -> None:
        self._root_dir = root_dir
        self._root_dir.mkdir(parents=True, exist_ok=True)

    def runs_path_for(self, session_key: str) -> Path:
        safe = _safe_name(session_key)
        if not safe:
            raise ValueError("invalid session_key")
        return self._root_dir / f"{safe}.jsonl"

    def create(self, record: RunRecord) -> RunRecord:
        """Append one run record."""
        path = self.runs_path_for(record.session_key)
        append_jsonl(path, record.to_json())
        return record

    def clone_session(self, source_session_key: str, target_session_key: str) -> int:
        """Copy all durable run records from one session into another."""
        copied = 0
        for record in self.list_for_session(source_session_key, limit=10_000):
            cloned = RunRecord(
                run_id=record.run_id,
                session_key=target_session_key,
                provider=record.provider,
                model=record.model,
                status=record.status,
                user_message=record.user_message,
                tool_execution_mode=record.tool_execution_mode,
                will_attempt_tool_loop=record.will_attempt_tool_loop,
                started_at=record.started_at,
                completed_at=record.completed_at,
                working_set=dict(record.working_set),
                message_count=record.message_count,
                input_token_estimate=record.input_token_estimate,
                tool_steps=[dict(step) for step in record.tool_steps],
                artifact_ids=list(record.artifact_ids),
                output_summary=record.output_summary,
                error=record.error,
                transition_reason=record.transition_reason,
                terminal_reason=record.terminal_reason,
                tool_results=[dict(item) for item in record.tool_results],
                pending_input_count=record.pending_input_count,
                oversized_tool_artifact_ids=list(record.oversized_tool_artifact_ids),
                metadata=dict(record.metadata),
            )
            self.create(cloned)
            copied += 1
        return copied

    def list_for_session(self, session_key: str, limit: int = 50) -> list[RunRecord]:
        """Return recent run records for one session."""
        path = self.runs_path_for(session_key)
        if limit <= 0:
            return []
        with _path_lock(path):
            if not path.exists():
                return []
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
