"""USER.md proposal service: draft → operator review → section-merge.

The model proposes durable identity deltas with ``user.remember`` (capped per day so
it picks real deltas, not append-spam). The operator approves — merging the delta into
the active persona's USER.md — or discards. Approved proposals are retained so they
count toward the daily cap and can't be bypassed by propose→approve→propose.
"""

from __future__ import annotations

from uuid import uuid4

from copenet.core.persona.service import PersonaHomeService
from copenet.core.sessions.session_store import utc_now_iso
from copenet.core.user_notes.store import UserNoteProposal, UserNotesStore

DEFAULT_DAILY_LIMIT = 3


class UserNoteLimitReached(Exception):
    """Raised when the per-day USER.md proposal cap is hit."""


class UserNotesService:
    def __init__(
        self,
        *,
        store: UserNotesStore,
        persona_service: PersonaHomeService,
        daily_limit: int = DEFAULT_DAILY_LIMIT,
    ) -> None:
        self._store = store
        self._persona_service = persona_service
        self._daily_limit = daily_limit

    def list_proposals(self, *, status: str = "draft") -> list[UserNoteProposal]:
        rows = self._store.list_items()
        if status == "all":
            return rows
        return [item for item in rows if item.status == status]

    def count_today(self) -> int:
        today = utc_now_iso()[:10]
        return sum(1 for item in self._store.list_items() if item.created_at[:10] == today)

    def propose_user_note(
        self,
        *,
        target_section: str,
        summary: str,
        body: str,
        last_session_key: str | None = None,
    ) -> UserNoteProposal:
        """Create a draft USER.md delta. Raises UserNoteLimitReached at the daily cap.

        Counts drafts AND approved notes from today, so the cap can't be sidestepped
        by approving and re-proposing within the same day.
        """
        if self.count_today() >= self._daily_limit:
            raise UserNoteLimitReached(
                f"daily USER.md update limit reached ({self._daily_limit}/day)"
            )
        now = utc_now_iso()
        record = UserNoteProposal(
            id=f"usernote-{uuid4()}",
            target_section=(target_section or "Summary").strip() or "Summary",
            summary=summary.strip() or "USER.md update",
            body=body.strip(),
            status="draft",
            created_at=now,
            updated_at=now,
            last_session_key=last_session_key,
        )
        return self._store.upsert(record)

    def approve_user_note(
        self,
        note_id: str,
        *,
        target_section: str | None = None,
        summary: str | None = None,
        body: str | None = None,
    ) -> UserNoteProposal | None:
        """Merge a draft into USER.md (optionally with operator edits) and mark approved."""
        existing = self._store.get(note_id)
        if existing is None:
            return None
        merged_section = (target_section if target_section is not None else existing.target_section).strip() or "Summary"
        merged_body = (body if body is not None else existing.body).strip()
        self._persona_service.merge_user_md_section(target_section=merged_section, body=merged_body)
        approved = UserNoteProposal(
            id=existing.id,
            target_section=merged_section,
            summary=(summary if summary is not None else existing.summary).strip() or "USER.md update",
            body=merged_body,
            status="approved",
            created_at=existing.created_at,
            updated_at=utc_now_iso(),
            last_session_key=existing.last_session_key,
        )
        return self._store.upsert(approved)

    def discard_user_note(self, note_id: str) -> bool:
        return self._store.delete(note_id)
