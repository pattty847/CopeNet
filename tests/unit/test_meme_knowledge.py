from __future__ import annotations

from pathlib import Path

from copenet.core.meme_knowledge import build_meme_knowledge_index, build_meme_knowledge_pack


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _seed_library(root: Path) -> None:
    _write(
        root / "Voice Map.md",
        """# Voice Map\n\n## Core voice traits\n- deadpan delivery of ridiculous jargon\n- fake-expert certainty\n\n## Risks / what to avoid\n- sounding like a normie explaining the joke\n- over-structuring captions until they lose chaos\n""",
    )
    _write(
        root / "Humor Mechanisms.md",
        """# Humor Mechanisms\n\n## Faux-clinical overanalysis\nDescribe a normal image as if it reveals biological failure.\n\n## Cadence-first gibberish parody\nPreserve rhythm while corrupting the content into semi-coherent nonsense.\n""",
    )
    _write(
        root / "Meme Engines.md",
        """# Meme Engines\n\n## Political inversion\nUse bootstrap rhetoric on institutions.\n\n## Institutional brainrot\nTranslate cursed behavior into polished memo language.\n""",
    )
    _write(
        root / "Caption Pattern Bank.md",
        """# Caption Pattern Bank\n\n## Pattern 1\nvisual cue -> biological inference -> status implication\n""",
    )
    _write(
        root / "Human Nuance Capture.md",
        """# Human Nuance Capture\n\n## Core principle\nA meme is not just image plus caption. Hidden lore matters.\n""",
    )
    _write(
        root / "Topical Memeifier.md",
        """# Topical Memeifier\n\n## Workflow\nStart from contradiction and choose the engine instead of memeing the headline directly.\n""",
    )
    _write(
        root / "Subculture Lexicon - Looksmaxxing Mogging.md",
        """# Subculture Lexicon - Looksmaxxing Mogging\n\n- clavicular\n- mogging\n- low T\n- cortisol spike\n""",
    )
    _write(
        root / "Feedback" / "2026-04-18-post-bank-feedback.md",
        """# Post bank feedback\n\n## Updated rules from Pat feedback\nLess abstract, more artifact. Avoid repackaged quirky slogan energy.\n""",
    )
    _write(
        root / "Case Studies" / "2026-04-19-sports-talk-gibberish-parody.md",
        """# Sports talk gibberish parody\n\n## Why it works\nCadence-first gibberish parody with fake stat rhythm and overconfident analysis.\n""",
    )


def test_build_meme_knowledge_index_normalizes_docs_and_writes_cache(tmp_path: Path) -> None:
    root = tmp_path / "library"
    cache_path = tmp_path / "cache" / "index.json"
    _seed_library(root)

    context = build_meme_knowledge_index(root, cache_path)

    assert len(context.documents) >= 8
    assert cache_path.exists()
    assert {doc.doc_type for doc in context.documents} >= {"voice_map", "humor_mechanism", "case_study", "feedback_rule"}


def test_build_meme_knowledge_pack_biases_image_shell_and_subculture(tmp_path: Path) -> None:
    root = tmp_path / "library"
    _seed_library(root)
    context = build_meme_knowledge_index(root, tmp_path / "cache" / "index.json")

    pack = build_meme_knowledge_pack(
        context,
        topic="clavicular mogging emergency",
        trend_summary=None,
        image_springboard="mirror selfie with suspicious posture",
        tone_hints=["copecore", "dry"],
    )

    assert pack.voice_summary
    assert pack.mechanism_pack
    assert pack.lexicon_pack
    assert pack.artifact_shell_pack[0] == "reaction image overlay"


def test_build_meme_knowledge_pack_biases_topical_and_cadence_queries(tmp_path: Path) -> None:
    root = tmp_path / "library"
    _seed_library(root)
    context = build_meme_knowledge_index(root, tmp_path / "cache" / "index.json")

    pack = build_meme_knowledge_pack(
        context,
        topic="sports desk hysteria",
        trend_summary="institutional talking points around a temporary operation",
        image_springboard=None,
        tone_hints=["edgy"],
    )

    joined = " ".join(excerpt.summary.lower() for excerpt in pack.engine_pack + pack.case_study_pack)
    assert "contradiction" in joined or "cadence" in joined or "analysis" in joined
    assert pack.artifact_shell_pack[0] in {"internal memo", "press quote", "policy notice", "fake commentary graphic"}
