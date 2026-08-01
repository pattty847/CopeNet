"""Prompt and mutation-plan builders for meme ideation."""

from __future__ import annotations

from copenet.core.meme_knowledge import MemeKnowledgePack
from copenet.prompts.loader import get_prompt_text

from .meme_ideation_constants import (
    MEME_IDEATION_PRESET_ID,
    _DOMAIN_COLLISION_BANK,
    _PRESET_ALIASES,
    _PRESET_GUIDANCE,
    _STYLE_ANTI_PATTERNS,
)
from .meme_ideation_models import (
    MediaTranscriptPack,
    MemeIdeationRequest,
    MemeRefinementRequest,
    MutationPlan,
    _clean_optional_text,
    _normalize_text_items,
)


def _resolve_prompt_preset_id(preset: str) -> str:
    return _PRESET_ALIASES.get(preset, preset)


def load_meme_system_prompt(preset: str = MEME_IDEATION_PRESET_ID) -> str:
    resolved_preset = _resolve_prompt_preset_id(preset)
    text = get_prompt_text("meme-ideation", resolved_preset)
    if text is None:
        raise ValueError(f"unknown meme ideation preset: {preset}")
    return text


def build_media_transcript_pack(
    *,
    title: str | None,
    transcript: str | None,
    transcript_source: str | None,
    transcript_excerpt: str | None,
) -> MediaTranscriptPack:
    clean_title = _clean_optional_text(title)
    clean_transcript = _clean_optional_text(transcript) or ""
    clean_excerpt = _clean_optional_text(transcript_excerpt)
    lines = [line.strip(" -\t") for line in clean_transcript.splitlines() if line.strip()]
    if not lines:
        sentences = [part.strip() for part in clean_transcript.replace("\r", "\n").split(".") if part.strip()]
        lines = sentences
    unique_lines: list[str] = []
    seen: set[str] = set()
    for line in lines:
        normalized = line.strip()
        if not normalized:
            continue
        lowered = normalized.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        unique_lines.append(normalized)
    key_lines = tuple(unique_lines[:3])
    notable_quotes = tuple(line for line in key_lines if len(line.split()) >= 2)[:2]
    if unique_lines:
        base_summary = " ".join(unique_lines[:2]).strip()
    else:
        base_summary = clean_excerpt or clean_title or "Imported media clip"
    if clean_title and clean_title.lower() not in base_summary.lower():
        summary = f"{clean_title}: {base_summary}"
    else:
        summary = base_summary
    tone_cues: list[str] = []
    lowered_blob = " ".join(unique_lines[:5]).lower()
    if "?" in clean_transcript:
        tone_cues.append("interrogative")
    if any(term in lowered_blob for term in ("bro", "dude", "man", "listen")):
        tone_cues.append("spoken")
    if any(term in lowered_blob for term in ("lock in", "discipline", "routine", "mindset")):
        tone_cues.append("motivational")
    return MediaTranscriptPack(
        summary=summary,
        key_lines=key_lines or tuple(filter(None, [clean_excerpt])),
        notable_quotes=notable_quotes or key_lines[:1],
        transcript_source=_clean_optional_text(transcript_source),
        transcript_excerpt=clean_excerpt,
        tone_cues=tuple(tone_cues),
    )


def _classify_style_mode(request: MemeIdeationRequest, knowledge_pack: MemeKnowledgePack) -> str:
    topic = " ".join(
        part
        for part in (
            request.topic or "",
            request.trend_summary or "",
            request.image_springboard or "",
            request.media_title or "",
            request.media_source_url or "",
            request.media_transcript_pack.summary if request.media_transcript_pack else "",
            " ".join(request.media_transcript_pack.key_lines) if request.media_transcript_pack else "",
            " ".join(request.tone_hints),
        )
        if part
    ).lower()
    if any(term in topic for term in ("sports", "commentary", "analyst", "ticker", "gibberish")):
        return "cadence-parody"
    if knowledge_pack.lexicon_pack and any(hint in {"copecore", "raw"} for hint in request.tone_hints):
        return "subculture"
    if any(term in topic for term in ("mog", "maxx", "cortisol", "low t", "clavicle", "aura", "phenotype", "streamer", "alpha")):
        return "subculture"
    if request.trend_summary and any(
        term in topic for term in ("temporary operation", "military", "war", "government", "policy", "politician", "institution", "mission creep")
    ):
        return "political-inversion"
    if request.image_springboard:
        return "image-shell"
    if request.trend_summary and any(term in topic for term in ("corporate", "office", "workplace", "manager", "hr", "memo")):
        return "institutional"
    if request.trend_summary:
        return "topical"
    return "default"


def build_mutation_plan(request: MemeIdeationRequest, knowledge_pack: MemeKnowledgePack) -> MutationPlan:
    style_mode = _classify_style_mode(request, knowledge_pack)
    domain_collisions = _DOMAIN_COLLISION_BANK.get(style_mode, _DOMAIN_COLLISION_BANK["default"])
    artifact_shells = knowledge_pack.artifact_shell_pack or ("image overlay", "sticky note", "receipt")
    if style_mode == "subculture":
        artifact_shells = ("screenshot annotation", "reaction image overlay", "comment screenshot", "quote card")
    elif style_mode == "political-inversion":
        artifact_shells = ("product label", "press quote", "policy notice", "protest sign")
    elif style_mode == "institutional":
        artifact_shells = ("sticky note", "performance review excerpt", "office sign", "internal memo")
    elif style_mode == "cadence-parody":
        artifact_shells = ("fake commentary graphic", "ticker chyron", "quote card", "screenshot annotation")
    escalation_mode = "first clause legible, second clause unreasonable"
    notes = [
        f"Style mode: {style_mode}.",
        "Every winning candidate should feel discovered instead of neatly written.",
        "Prefer artifact shells over freestanding slogan comedy.",
        "Start from a recognizable clue, then escalate into fake authority or impossible specificity.",
        "Do not default to neat corporate memo parody unless the brief clearly demands it.",
    ]
    if request.preset in _PRESET_GUIDANCE:
        notes.append(_PRESET_GUIDANCE[request.preset])
    return MutationPlan(
        style_mode=style_mode,
        artifact_shell_candidates=tuple(artifact_shells[:4]),
        domain_collision_candidates=tuple(domain_collisions[:4]),
        escalation_mode=escalation_mode,
        anti_pattern_bans=_STYLE_ANTI_PATTERNS,
        mutation_notes=tuple(notes),
    )


def _render_excerpt_block(label: str, excerpts: tuple[object, ...]) -> str:
    if not excerpts:
        return f"{label}: none"
    lines = [f"{label}:"]
    for excerpt in excerpts:
        lines.append(f"- {excerpt.title} / {excerpt.section_title}: {excerpt.summary}")
    return "\n".join(lines)


def build_meme_user_prompt(request: MemeIdeationRequest, knowledge_pack: MemeKnowledgePack | None = None, mutation_plan: MutationPlan | None = None) -> str:
    lines = [
        "Generate structured meme ideas for the operator's configured meme page.",
        f"Return exactly {request.requested_count} candidates as JSON using the required schema.",
    ]
    if request.media_asset_id:
        lines.append(f"mediaAssetId: {request.media_asset_id}")
    if request.media_title:
        lines.append(f"mediaTitle: {request.media_title}")
    if request.media_source_url:
        lines.append(f"mediaSourceUrl: {request.media_source_url}")
    if request.media_transcript_pack and request.media_transcript_pack.has_content:
        if request.media_transcript_pack.summary:
            lines.append(f"mediaTranscriptSummary: {request.media_transcript_pack.summary}")
        if request.media_transcript_pack.key_lines:
            lines.append(f"mediaKeyLines: {' | '.join(request.media_transcript_pack.key_lines)}")
        if request.media_transcript_pack.notable_quotes:
            lines.append(f"mediaNotableQuotes: {' | '.join(request.media_transcript_pack.notable_quotes)}")
        if request.media_transcript_pack.transcript_source:
            lines.append(f"mediaTranscriptSource: {request.media_transcript_pack.transcript_source}")
        if request.media_transcript_pack.tone_cues:
            lines.append(f"mediaToneCues: {', '.join(request.media_transcript_pack.tone_cues)}")
    if request.topic:
        lines.append(f"topic: {request.topic}")
    if request.trend_summary:
        lines.append(f"trendSummary: {request.trend_summary}")
    if request.image_springboard:
        lines.append(f"imageSpringboard: {request.image_springboard}")
    if request.tone_hints:
        lines.append(f"toneHints: {', '.join(request.tone_hints)}")
    preset_guidance = _PRESET_GUIDANCE.get(request.preset)
    if preset_guidance:
        lines.append(preset_guidance)
    if mutation_plan:
        lines.append(f"styleMode: {mutation_plan.style_mode}")
        lines.append(f"artifactShellCandidates: {', '.join(mutation_plan.artifact_shell_candidates)}")
        lines.append(f"domainCollisionCandidates: {', '.join(mutation_plan.domain_collision_candidates)}")
        lines.append(f"escalationMode: {mutation_plan.escalation_mode}")
    if knowledge_pack:
        lines.append(_render_excerpt_block("voiceSummary", knowledge_pack.voice_summary))
        lines.append(_render_excerpt_block("mechanismPack", knowledge_pack.mechanism_pack))
        lines.append(_render_excerpt_block("enginePack", knowledge_pack.engine_pack))
        lines.append(_render_excerpt_block("captionPatternPack", knowledge_pack.caption_pattern_pack))
        lines.append(_render_excerpt_block("feedbackPack", knowledge_pack.feedback_pack))
        lines.append(_render_excerpt_block("caseStudyPack", knowledge_pack.case_study_pack))
        if knowledge_pack.lexicon_pack:
            lines.append(_render_excerpt_block("lexiconPack", knowledge_pack.lexicon_pack))
    lines.append("Require at least one hyper-specific detail, at least one domain shift, and an escalation from legible to unreasonable in each candidate.")
    lines.append("When media transcript context is present, tie at least one candidate directly to the clip's narration, tone, or timing.")
    lines.append("Favor artifact-first outputs: receipt, sticky note, product label, quote card, screenshot annotation, internal memo, protest sign, or image overlay.")
    lines.append("Avoid neat consultant prose, fully grammatical corporate parody, and explanatory direction labels that tell the joke instead of embodying it.")
    lines.append("For subculture mode, prefer ugly interpretable compounds and faux-diagnostic wording over generic manosphere parody.")
    lines.append("For political inversion mode, prefer product packaging, official euphemism, notices, or contaminated consumer text over speechwriting.")
    lines.append(
        "Prioritize punchy meme directions, anti-quirky copy, compressed phrasing, fake authority, and discovered-sentence energy over polished joke writing."
    )
    return "\n".join(lines)


def build_meme_system_prompt(
    request: MemeIdeationRequest,
    *,
    knowledge_pack: MemeKnowledgePack,
    mutation_plan: MutationPlan,
) -> str:
    base_prompt = load_meme_system_prompt(request.preset)
    sections = [base_prompt]
    sections.append(
        "Taste directives:\n- discovered artifact over written copy\n- specific over smooth\n- unfairly compressed over quirky\n- image shell or object shell whenever possible\n- do not turn every prompt into a fake corporate memo\n- avoid polished explanatory captions"
    )
    sections.append("Anti-pattern bans:\n- " + "\n- ".join(mutation_plan.anti_pattern_bans))
    sections.append("Mutation notes:\n- " + "\n- ".join(mutation_plan.mutation_notes))
    if knowledge_pack.anti_patterns:
        sections.append(_render_excerpt_block("Anti-mid references", knowledge_pack.anti_patterns))
    if knowledge_pack.nuance_pack:
        sections.append(_render_excerpt_block("Human nuance", knowledge_pack.nuance_pack))
    return "\n\n".join(section for section in sections if section)


def build_meme_refinement_system_prompt(
    request: MemeRefinementRequest,
    *,
    knowledge_pack: MemeKnowledgePack,
    mutation_plan: MutationPlan,
) -> str:
    base_prompt = build_meme_system_prompt(request.ideation_request, knowledge_pack=knowledge_pack, mutation_plan=mutation_plan)
    extra = [
        "You are refining an existing meme post direction, not starting a generic chat.",
        "Respond as JSON with keys: assistantReply (string) and suggestedCandidates (array).",
        "assistantReply should be brief, concrete, and oriented around improving the post.",
        "suggestedCandidates should only include materially better rewrites or new directions, and may be empty.",
        "If media transcript context exists, tie the refinement directly to the clip's narration, tone, or timing.",
    ]
    return "\n\n".join([base_prompt, "Refinement directives:\n- " + "\n- ".join(extra)])


def build_meme_refinement_user_prompt(
    request: MemeRefinementRequest,
    *,
    knowledge_pack: MemeKnowledgePack,
    mutation_plan: MutationPlan,
) -> str:
    lines = [build_meme_user_prompt(request.ideation_request, knowledge_pack=knowledge_pack, mutation_plan=mutation_plan)]
    if request.current_generation_summary:
        lines.append(f"currentGenerationSummary: {request.current_generation_summary}")
    if request.current_candidates:
        lines.append("currentCandidates:")
        for index, candidate in enumerate(request.current_candidates, start=1):
            lines.append(
                f"- {index}. direction={candidate.direction}; format={candidate.format}; text={candidate.text}; "
                f"optionalCaption={candidate.optional_caption or 'none'}; notes={candidate.notes or 'none'}"
            )
    if request.chat_history:
        lines.append("refinementHistory:")
        for message in request.chat_history[-6:]:
            lines.append(f"- {message.role}: {message.content}")
    lines.append(f"latestUserMessage: {request.latest_user_message}")
    lines.append("Return a concise assistantReply plus only the strongest suggestedCandidates.")
    return "\n".join(lines)
