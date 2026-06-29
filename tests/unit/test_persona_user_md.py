"""Two-tier USER.md injection: compressed ## Summary loads every turn; the rest
of the file is read on demand, advertised by a synthetic section-index line."""

from __future__ import annotations

from pathlib import Path

from copenet.core.persona.service import PersonaHomeService, _compress_user_md


SAMPLE = """# USER.md

## Summary
Pat is a Philly-area builder. Deeper detail in body sections.

## Markets
Order book heatmaps, DXY, liquidity traps.

## Meme voice
Deadpan, anti-corny.
"""


def test_compress_splits_summary_from_body_titles() -> None:
    summary, titles = _compress_user_md(SAMPLE)
    assert summary == "Pat is a Philly-area builder. Deeper detail in body sections."
    assert titles == ["Markets", "Meme voice"]


def test_compress_falls_back_to_preamble_without_summary() -> None:
    summary, titles = _compress_user_md("# USER.md\n\nPrivate operator context belongs here.")
    assert summary == "Private operator context belongs here."
    assert titles == []


def test_build_prompt_context_injects_summary_and_index_not_body(tmp_path: Path) -> None:
    service = PersonaHomeService(root_dir=tmp_path)
    service._ensure_scaffold()
    user_path = tmp_path / "default" / "user" / "USER.md"
    user_path.write_text(SAMPLE, encoding="utf-8")

    context = service.build_prompt_context(provider="fake", model="m", privacy_tier="private", query="")

    # Tier 1: summary injects every turn.
    assert "Pat is a Philly-area builder" in context.prompt
    # Tier 2: body sections do NOT inject; the index advertises them + the readable path.
    assert "Order book heatmaps" not in context.prompt
    assert "Sections available on demand: Markets, Meme voice" in context.prompt
    assert str(user_path) in context.prompt


def test_safe_tier_excludes_user_md(tmp_path: Path) -> None:
    service = PersonaHomeService(root_dir=tmp_path)
    service._ensure_scaffold()
    (tmp_path / "default" / "user" / "USER.md").write_text(SAMPLE, encoding="utf-8")

    context = service.build_prompt_context(provider="fake", model="m", privacy_tier="safe", query="")

    assert "Pat is a Philly-area builder" not in context.prompt
    assert "USER.md sections" not in context.prompt
