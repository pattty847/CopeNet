"""Return-briefing builder — the "I'm back" Home orientation surface.

Builds the activity feed ("what CopeNet did while you were away") from durable run
records. Extracted from the retired Pat Profile system: attention/watch/notice were
driven by the deleted auto-extraction stores, so this builds the run-store-backed
``activity_items`` and leaves the others empty. The Persona Home USER.md ``## Summary``
may repopulate ``notice_text`` later; the wire shape stays identical for the frontend.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4

from copenet.core.runtime import RunRecord, RunStore
from copenet.core.sessions.session_store import utc_now_iso


@dataclass(frozen=True)
class BriefingAttentionItem:
    id: str
    title: str
    urgency: str
    source: str
    detail: str | None = None

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "urgency": self.urgency,
            "source": self.source,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class BriefingActivityItem:
    id: str
    summary: str
    session_key: str | None
    tools_used: int | None
    at: str

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "summary": self.summary,
            "sessionKey": self.session_key,
            "toolsUsed": self.tools_used,
            "at": self.at,
        }


@dataclass(frozen=True)
class BriefingWatchItem:
    id: str
    label: str
    signal: str
    source: str | None = None

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "signal": self.signal,
            "source": self.source,
        }


@dataclass(frozen=True)
class ReturnBriefingPayload:
    briefing_id: str
    generated_at: str
    attention_items: list[BriefingAttentionItem] = field(default_factory=list)
    activity_items: list[BriefingActivityItem] = field(default_factory=list)
    watch_items: list[BriefingWatchItem] = field(default_factory=list)
    notice_text: str | None = None
    notice_source: str | None = None

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "briefingId": self.briefing_id,
            "generatedAt": self.generated_at,
            "attentionItems": [item.to_public_dict() for item in self.attention_items],
            "activityItems": [item.to_public_dict() for item in self.activity_items],
            "watchItems": [item.to_public_dict() for item in self.watch_items],
            "noticeText": self.notice_text,
            "noticeSource": self.notice_source,
        }


class ReturnBriefingService:
    """Builds the return briefing from durable run records."""

    def __init__(self, *, run_store: RunStore) -> None:
        self._run_store = run_store

    def build_return_briefing(self) -> ReturnBriefingPayload | None:
        runs = self._list_recent_runs(limit=5)
        if not runs:
            return None

        activity_items = [
            BriefingActivityItem(
                id=record.run_id,
                summary=record.output_summary or record.user_message,
                session_key=record.session_key,
                tools_used=len(record.tool_steps),
                at=record.completed_at or record.started_at,
            )
            for record in runs[:3]
        ]

        return ReturnBriefingPayload(
            briefing_id=str(uuid4()),
            generated_at=utc_now_iso(),
            attention_items=[],
            activity_items=activity_items,
            watch_items=[],
            notice_text=None,
            notice_source=None,
        )

    def _list_recent_runs(self, *, limit: int = 10) -> list[RunRecord]:
        root = Path(self._run_store._root_dir)
        rows: list[RunRecord] = []
        for path in sorted(root.glob("*.jsonl")):
            for record in self._run_store.list_for_session(path.stem, limit=limit):
                rows.append(record)
        rows.sort(key=lambda item: item.completed_at or item.started_at, reverse=True)
        return rows[:limit]
