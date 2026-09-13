"""Read the active answer without mutating the append-only transcript."""

from __future__ import annotations

from .run_events import _streaming_message_parts
from .run_types import RunAdmission, RunEvents


class LiveHistory:
    def __init__(self) -> None:
        self.runs: dict[str, tuple[RunAdmission, RunEvents]] = {}

    def snapshot(self, session_key: str) -> dict | None:
        active = self.runs.get(session_key)
        if active is None:
            return None
        admission, events = active
        if events.transcript_persisted:
            return None
        return {
            "runId": admission.run_id,
            "seq": events.seq,
            "message": {
                "runId": admission.run_id,
                "role": "assistant",
                "state": "delta",
                "content": "".join(events.assistant_parts),
                "parts": _streaming_message_parts(events.assistant_message_parts),
                "timestamp": admission.run_started_at,
                "provider": admission.provider_name,
                "model": events.resolved_model or admission.request.model,
            },
        }
