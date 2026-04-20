from __future__ import annotations

from pathlib import Path

from copenet.core.meme_ideation import (
    MEME_IDEATION_PRESET_ID,
    MemeIdeationCandidate,
    MemeIdeationRequest,
    build_meme_system_prompt,
    build_meme_user_prompt,
    build_mutation_plan,
    judge_candidate,
    load_meme_system_prompt,
    parse_meme_ideation_output,
)
from copenet.core.meme_knowledge import build_meme_knowledge_index, build_meme_knowledge_pack


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _seed_library(root: Path) -> None:
    _write(root / "Voice Map.md", "# Voice Map\n\n## Core\n- deadpan\n- fake authority\n\n## Risks / what to avoid\n- sounding like a normie explaining the joke\n")
    _write(root / "Humor Mechanisms.md", "# Humor Mechanisms\n\n## Faux-clinical overanalysis\nVisible cue to biological failure.\n\n## Cadence-first gibberish parody\nKeep commentator rhythm.\n")
    _write(root / "Meme Engines.md", "# Meme Engines\n\n## Institutional brainrot\nTranslate cursed behavior into memo language.\n")
    _write(root / "Caption Pattern Bank.md", "# Caption Pattern Bank\n\n## Pattern\nvisual cue -> fake diagnosis -> collapse\n")
    _write(root / "Human Nuance Capture.md", "# Human Nuance Capture\n\n## Goal\nCapture hidden lore.\n")
    _write(root / "Feedback" / "2026-04-18-post-bank-feedback.md", "# Feedback\n\n## Rules\nAvoid quirky slogan energy. More artifact, less abstraction.\n")
    _write(root / "Subculture Lexicon - Looksmaxxing Mogging.md", "# Lexicon\n\n- mogging\n- clavicular\n- cortisol spike\n")
    _write(root / "Case Studies" / "2026-04-18-clavicular-mugshot-meme.md", "# Case Study\n\n## Why it works\nDense diagnostic chain with justicemogged collapse.\n")


def _knowledge_pack(tmp_path: Path):
    root = tmp_path / "library"
    _seed_library(root)
    context = build_meme_knowledge_index(root, tmp_path / "cache" / "index.json")
    request = MemeIdeationRequest(
        topic="discipline posting",
        trend_summary="three weeks of routine content turning into moral superiority",
        image_springboard="guy in a mirror selfie acting like an authority on human worth",
        tone_hints=["copecore", "dry"],
        requested_count=4,
        preset="sharpshooter",
    )
    pack = build_meme_knowledge_pack(
        context,
        topic=request.topic,
        trend_summary=request.trend_summary,
        image_springboard=request.image_springboard,
        tone_hints=request.tone_hints,
    )
    return request, pack


def test_build_meme_user_prompt_minimal_request() -> None:
    request = MemeIdeationRequest(topic="office burnout", requested_count=3)

    prompt = build_meme_user_prompt(request)

    assert "office burnout" in prompt
    assert "Return exactly 3 candidates" in prompt
    assert "trendSummary" not in prompt


def test_build_meme_user_prompt_full_request_with_retrieval_context(tmp_path: Path) -> None:
    request, pack = _knowledge_pack(tmp_path)
    mutation_plan = build_mutation_plan(request, pack)

    prompt = build_meme_user_prompt(request, pack, mutation_plan)

    assert "Preset mode: sharpshooter" in prompt
    assert "artifactShellCandidates" in prompt
    assert "voiceSummary:" in prompt
    assert "feedbackPack:" in prompt
    assert "Require at least one hyper-specific detail" in prompt


def test_build_meme_system_prompt_includes_anti_mid_pressure(tmp_path: Path) -> None:
    request, pack = _knowledge_pack(tmp_path)
    mutation_plan = build_mutation_plan(request, pack)

    prompt = build_meme_system_prompt(request, knowledge_pack=pack, mutation_plan=mutation_plan)

    assert "Anti-pattern bans" in prompt
    assert "no quirky brand voice" in prompt
    assert "Human nuance" in prompt


def test_build_mutation_plan_classifies_and_extracts_candidates(tmp_path: Path) -> None:
    request, pack = _knowledge_pack(tmp_path)

    plan = build_mutation_plan(request, pack)

    assert plan.style_mode in {"topical", "image-shell", "institutional", "subculture"}
    assert len(plan.domain_collision_candidates) >= 2
    assert plan.artifact_shell_candidates
    assert plan.escalation_mode


def test_alias_preset_resolves_to_default_system_prompt() -> None:
    assert load_meme_system_prompt("sharpshooter") == load_meme_system_prompt("meme-ideation")


def test_request_defaults_preset_and_normalizes_string_tone_hints() -> None:
    request = MemeIdeationRequest(
        image_springboard="guy smiling through pain at his portfolio",
        tone_hints="dry nihilism",
        requested_count=2,
    )

    assert request.preset == MEME_IDEATION_PRESET_ID
    assert request.tone_hints == ["dry nihilism"]


def test_judge_candidate_penalizes_generic_copy_and_rewards_artifact_heavy_output(tmp_path: Path) -> None:
    request, pack = _knowledge_pack(tmp_path)
    mutation_plan = build_mutation_plan(request, pack)
    strong = MemeIdeationCandidate(
        direction="forensic memo",
        format="receipt",
        text="ROTATED THE FRY 12 DEGREES AND NOW IT COUNTS AS A DIFFERENT ASSET CLASS / before the allocation committee notices",
        optional_caption=None,
        needs_visual_context=True,
        notes="works as a receipt footer",
    )
    weak = MemeIdeationCandidate(
        direction="relatable joke",
        format="one-liner",
        text="just another office burnout moment",
        optional_caption=None,
        needs_visual_context=False,
        notes=None,
    )

    strong_score = judge_candidate(strong, candidate_index=0, mutation_plan=mutation_plan)
    weak_score = judge_candidate(weak, candidate_index=1, mutation_plan=mutation_plan)

    assert strong_score.accepted is True
    assert weak_score.accepted is False
    assert weak_score.normie_contamination_risk > strong_score.normie_contamination_risk


def test_parse_meme_ideation_output_accepts_strict_json() -> None:
    raw = """
    {
      "candidates": [
        {
          "direction": "Overconfident opener",
          "format": "top_bottom_text",
          "text": "ME BUYING THE DIP / THE DIP HAVING A BASEMENT",
          "optional_caption": "average Tuesday",
          "needs_visual_context": false,
          "notes": "works as a classic market meme"
        }
      ]
    }
    """.strip()

    result = parse_meme_ideation_output(raw, debug=False)

    assert result.candidates == [
        MemeIdeationCandidate(
            direction="Overconfident opener",
            format="top_bottom_text",
            text="ME BUYING THE DIP / THE DIP HAVING A BASEMENT",
            optional_caption="average Tuesday",
            needs_visual_context=False,
            notes="works as a classic market meme",
        )
    ]
    assert result.warnings == []
    assert result.raw_text is None


def test_parse_meme_ideation_output_returns_raw_text_only_when_debug_enabled() -> None:
    raw = "definitely not json"

    result = parse_meme_ideation_output(raw, debug=True)

    assert result.candidates == []
    assert result.warnings
    assert result.raw_text == raw
