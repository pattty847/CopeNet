"""user.remember draft flow: propose (capped) → approve (section-merge) → discard."""

from __future__ import annotations

from pathlib import Path

import pytest

from copenet.core.persona.service import PersonaHomeService
from copenet.core.user_notes import UserNoteLimitReached, UserNotesService, UserNotesStore


def _service(tmp_path: Path, *, daily_limit: int = 3) -> tuple[UserNotesService, PersonaHomeService]:
    persona = PersonaHomeService(root_dir=tmp_path / "personas")
    persona._ensure_scaffold()
    persona.user_md_path().write_text("# USER.md\n\n## Summary\nPat builds things.\n", encoding="utf-8")
    store = UserNotesStore(path=tmp_path / "user-notes.json")
    return UserNotesService(store=store, persona_service=persona, daily_limit=daily_limit), persona


def test_propose_creates_draft_not_written_to_user_md(tmp_path: Path) -> None:
    service, persona = _service(tmp_path)
    proposal = service.propose_user_note(target_section="Projects", summary="add projects", body="Sentinel, CopeNet.")
    assert proposal.status == "draft"
    assert service.list_proposals(status="draft") == [proposal]
    # Draft is NOT in USER.md until approved.
    assert "Sentinel" not in persona.user_md_path().read_text(encoding="utf-8")


def test_daily_cap_blocks_after_limit_counting_drafts_and_approved(tmp_path: Path) -> None:
    service, _ = _service(tmp_path, daily_limit=2)
    first = service.propose_user_note(target_section="Projects", summary="s", body="a")
    service.propose_user_note(target_section="Markets", summary="s", body="b")
    with pytest.raises(UserNoteLimitReached):
        service.propose_user_note(target_section="Cyber", summary="s", body="c")
    # Approving doesn't free a slot — approved-today still counts toward the cap.
    service.approve_user_note(first.id)
    assert service.count_today() == 2
    with pytest.raises(UserNoteLimitReached):
        service.propose_user_note(target_section="Cyber", summary="s", body="c")


def test_approve_merges_section_leaving_others_intact(tmp_path: Path) -> None:
    service, persona = _service(tmp_path)
    proposal = service.propose_user_note(target_section="Projects", summary="add", body="Sentinel, CopeNet.")
    approved = service.approve_user_note(proposal.id)
    assert approved is not None and approved.status == "approved"
    text = persona.user_md_path().read_text(encoding="utf-8")
    assert "## Projects\nSentinel, CopeNet." in text
    assert "## Summary\nPat builds things." in text  # untouched


def test_approve_replaces_existing_section_not_append(tmp_path: Path) -> None:
    service, persona = _service(tmp_path)
    proposal = service.propose_user_note(target_section="Summary", summary="tighten", body="Pat ships systems.")
    service.approve_user_note(proposal.id)
    text = persona.user_md_path().read_text(encoding="utf-8")
    assert text.count("## Summary") == 1
    assert "Pat ships systems." in text
    assert "Pat builds things." not in text


def test_discard_removes_draft(tmp_path: Path) -> None:
    service, _ = _service(tmp_path)
    proposal = service.propose_user_note(target_section="Projects", summary="s", body="a")
    assert service.discard_user_note(proposal.id) is True
    assert service.list_proposals(status="draft") == []
