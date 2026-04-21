"""Stateless meme ideation prompt, retrieval, judging, and provider orchestration."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field, replace

from copenet.core.meme_knowledge import (
    MemeKnowledgePack,
    build_meme_knowledge_index,
    build_meme_knowledge_pack,
)
from copenet.prompts.loader import get_prompt_text
from copenet.providers.base import Provider


MEME_IDEATION_PRESET_ID = "meme-ideation"
MEME_IDEATION_PROMPT_VERSION = "meme-ideation-v2"
MEME_IDEATION_SCHEMA_VERSION = "v1"
_MAX_REQUESTED_COUNT = 8
_LOCAL_PROVIDER_IDS = {"lm-studio", "ollama"}
_PRESET_ALIASES = {
    "shotgun": MEME_IDEATION_PRESET_ID,
    "sharpshooter": MEME_IDEATION_PRESET_ID,
    "remix": MEME_IDEATION_PRESET_ID,
    "cold-open": MEME_IDEATION_PRESET_ID,
}
_PRESET_GUIDANCE = {
    "shotgun": "Preset mode: shotgun. Push for breadth, divergence, and noticeably different comedic angles.",
    "sharpshooter": "Preset mode: sharpshooter. Favor sharper, more polished candidates and avoid filler variations.",
    "remix": "Preset mode: remix. Riff directly on the provided trend summary or image springboard instead of inventing from nowhere.",
    "cold-open": "Preset mode: cold-open. Build from first principles and do not depend on assumed meme lore or current trend context.",
}
_DOMAIN_COLLISION_BANK = {
    "topical": ("compliance", "finance", "military analysis", "press briefing"),
    "image-shell": ("medical diagnostics", "forensic review", "product QA", "insurance adjuster"),
    "subculture": ("endocrinology", "sports commentary", "eugenics powerpoint", "ritual ranking board"),
    "institutional": ("HR", "consulting", "board meeting", "policy rollout"),
    "political-inversion": ("landlord logic", "corporate subsidy", "national operations memo", "temporary mission management"),
    "cadence-parody": ("sports desk", "trading floor", "podcast clip", "film room breakdown"),
    "default": ("aerospace QA", "religious ritual", "SEC filing", "discharge summary"),
}
_STYLE_ANTI_PATTERNS = (
    "no hashtags",
    "no emoji padding",
    "no broad relatable office humor",
    "no polished slogan copy",
    "no normie explanation",
    "no named mainstream meme templates unless the brief explicitly asks for them",
    "no quirky brand voice",
)
_FAKE_AUTHORITY_WORDS = {
    "protocol",
    "allocation",
    "review",
    "committee",
    "compliance",
    "diagnostic",
    "manager",
    "findings",
    "guidance",
    "memo",
    "forensic",
    "tier",
    "briefing",
    "coverage",
}
_NORMIE_RISK_PHRASES = {
    "just another",
    "adulting",
    "relatable",
    "monday mood",
    "office burnout",
    "when you",
    "the difference between",
    "me trying to",
    "current status",
    "recommend immediate",
    "status update",
    "if you aren't",
    "it started as",
}
_ARTIFACT_FORMATS = {
    "receipt",
    "fortune_cookie",
    "fortune cookie",
    "sticky note",
    "job listing",
    "product label",
    "quote card",
    "image overlay",
    "comment screenshot",
    "protest sign",
    "reaction_caption",
    "tweet_screenshot",
    "screenshot_overlay",
    "screenshot annotation",
    "internal memo",
}
_DOMAIN_KEYWORDS = {
    "finance": {"allocation", "asset", "filing", "equity", "committee", "front-running"},
    "compliance": {"compliance", "review", "policy", "guidance", "flagged"},
    "medical diagnostics": {"diagnostic", "syndrome", "sample", "load", "stress test", "discharge"},
    "forensic review": {"forensic", "evidence", "chain", "artifact", "findings"},
    "product QA": {"sample", "collapse", "stress test", "calibration", "defect"},
    "insurance adjuster": {"claim", "liability", "exposure", "review"},
    "endocrinology": {"cortisol", "low t", "hormonal", "endocrine"},
    "sports commentary": {"film room", "coverage", "line", "completion", "analyst"},
    "eugenics powerpoint": {"phenotype", "metrics", "tier", "slide"},
    "ritual ranking board": {"rite", "initiation", "officiant", "ranking"},
    "HR": {"workplace", "conduct", "manager", "policy", "escalation"},
    "consulting": {"deliverable", "stakeholder", "rollout", "committee"},
    "board meeting": {"board", "agenda", "shareholder", "oversight"},
    "policy rollout": {"pilot", "rollout", "implementation", "memo"},
    "landlord logic": {"tenant", "rent", "maintenance", "notice"},
    "corporate subsidy": {"subsidy", "corporate", "relief", "dependency"},
    "national operations memo": {"operation", "temporary", "region", "escalation"},
    "temporary mission management": {"temporary", "mission", "extension", "coordination"},
    "sports desk": {"desk", "analyst", "tape", "highlight"},
    "trading floor": {"floor", "ticker", "allocation", "filing"},
    "podcast clip": {"clip", "episode", "authority", "panel"},
    "film room breakdown": {"film", "breakdown", "angle", "coverage"},
    "aerospace QA": {"stress test", "load", "flight", "tolerance"},
    "religious ritual": {"rite", "liturgy", "officiant", "blessing"},
    "SEC filing": {"sec", "disclosure", "filing", "committee"},
    "discharge summary": {"discharge", "summary", "evaluation", "acute"},
}
_REWRITE_DETAILS = {
    "aerospace QA": "after the 14-sample load test folded at the tip",
    "religious ritual": "pending minor rite approval",
    "SEC filing": "before the disclosure committee sees it",
    "discharge summary": "pending discharge review",
    "medical diagnostics": "after diagnostic review",
    "forensic review": "per forensic findings",
    "product QA": "once the calibration report lands",
    "insurance adjuster": "after liability review",
    "endocrinology": "pending endocrine review",
    "sports commentary": "after film room review",
    "HR": "per workplace conduct guidance",
    "consulting": "during the rollout window",
    "board meeting": "before it hits the agenda",
    "policy rollout": "during implementation review",
    "compliance": "under compliance review",
    "finance": "before the allocation committee notices",
}


@dataclass(frozen=True)
class MemeIdeationCandidate:
    direction: str
    format: str
    text: str
    optional_caption: str | None = None
    needs_visual_context: bool = False
    notes: str | None = None


@dataclass(frozen=True)
class MemeIdeationParseResult:
    candidates: list[MemeIdeationCandidate]
    warnings: list[str] = field(default_factory=list)
    raw_text: str | None = None


@dataclass(frozen=True)
class MediaTranscriptPack:
    summary: str | None = None
    key_lines: tuple[str, ...] = ()
    notable_quotes: tuple[str, ...] = ()
    transcript_source: str | None = None
    transcript_excerpt: str | None = None
    tone_cues: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        summary = _clean_optional_text(self.summary)
        key_lines = tuple(_normalize_text_items(self.key_lines))
        notable_quotes = tuple(_normalize_text_items(self.notable_quotes))
        transcript_source = _clean_optional_text(self.transcript_source)
        transcript_excerpt = _clean_optional_text(self.transcript_excerpt)
        tone_cues = tuple(_normalize_text_items(self.tone_cues))
        object.__setattr__(self, "summary", summary)
        object.__setattr__(self, "key_lines", key_lines)
        object.__setattr__(self, "notable_quotes", notable_quotes)
        object.__setattr__(self, "transcript_source", transcript_source)
        object.__setattr__(self, "transcript_excerpt", transcript_excerpt)
        object.__setattr__(self, "tone_cues", tone_cues)

    @property
    def has_content(self) -> bool:
        return bool(self.summary or self.key_lines or self.notable_quotes or self.transcript_excerpt)


@dataclass(frozen=True)
class MutationPlan:
    style_mode: str
    artifact_shell_candidates: tuple[str, ...]
    domain_collision_candidates: tuple[str, ...]
    escalation_mode: str
    anti_pattern_bans: tuple[str, ...]
    mutation_notes: tuple[str, ...]


@dataclass(frozen=True)
class JudgeScorecard:
    candidate_index: int
    artifact_shell_strength: float
    lexical_novelty: float
    domain_collision_strength: float
    delayed_recognition: float
    fake_authority_energy: float
    implied_lore_density: float
    normie_contamination_risk: float
    total_score: float
    accepted: bool
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class MemeRefinementMessage:
    role: str
    content: str

    def __post_init__(self) -> None:
        role = _clean_optional_text(self.role) or "user"
        content = _clean_optional_text(self.content)
        if content is None:
            raise ValueError("refinement message content is required")
        object.__setattr__(self, "role", role)
        object.__setattr__(self, "content", content)


@dataclass(frozen=True)
class MemeRefinementParseResult:
    assistant_reply: str
    suggested_candidates: list[MemeIdeationCandidate]
    warnings: list[str] = field(default_factory=list)
    raw_text: str | None = None


@dataclass(frozen=True)
class MemeIdeationResponse:
    candidates: list[MemeIdeationCandidate]
    provider: str
    model: str
    preset: str
    schema_version: str
    prompt_version: str
    warnings: list[str] = field(default_factory=list)
    raw_text: str | None = None
    knowledge_pack_version: str | None = None
    judge_warnings: list[str] = field(default_factory=list)
    artifact_shell: str | None = None
    mutation_notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class MemeRefinementResponse:
    assistant_reply: str
    suggested_candidates: list[MemeIdeationCandidate]
    provider: str
    model: str
    preset: str
    schema_version: str
    prompt_version: str
    warnings: list[str] = field(default_factory=list)
    raw_text: str | None = None
    knowledge_pack_version: str | None = None
    judge_warnings: list[str] = field(default_factory=list)
    artifact_shell: str | None = None
    mutation_notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class MemeIdeationRequest:
    topic: str | None = None
    trend_summary: str | None = None
    image_springboard: str | None = None
    tone_hints: str | list[str] | None = None
    requested_count: int = 3
    provider: str | None = None
    model: str | None = None
    preset: str = MEME_IDEATION_PRESET_ID
    media_asset_id: str | None = None
    media_title: str | None = None
    media_source_url: str | None = None
    media_transcript_pack: MediaTranscriptPack | None = None
    debug: bool = False

    def __post_init__(self) -> None:
        topic = _clean_optional_text(self.topic)
        trend_summary = _clean_optional_text(self.trend_summary)
        image_springboard = _clean_optional_text(self.image_springboard)
        preset = _clean_optional_text(self.preset) or MEME_IDEATION_PRESET_ID
        provider = _clean_optional_text(self.provider)
        model = _clean_optional_text(self.model)
        media_asset_id = _clean_optional_text(self.media_asset_id)
        media_title = _clean_optional_text(self.media_title)
        media_source_url = _clean_optional_text(self.media_source_url)
        media_transcript_pack = _normalize_media_transcript_pack(self.media_transcript_pack)
        tone_hints = _normalize_tone_hints(self.tone_hints)
        requested_count = int(self.requested_count)

        if not any((topic, trend_summary, image_springboard, media_title, media_source_url, media_transcript_pack and media_transcript_pack.has_content)):
            raise ValueError("at least one of topic, trend_summary, image_springboard, or media context is required")
        if requested_count < 1 or requested_count > _MAX_REQUESTED_COUNT:
            raise ValueError(f"requested_count must be between 1 and {_MAX_REQUESTED_COUNT}")

        object.__setattr__(self, "topic", topic)
        object.__setattr__(self, "trend_summary", trend_summary)
        object.__setattr__(self, "image_springboard", image_springboard)
        object.__setattr__(self, "tone_hints", tone_hints)
        object.__setattr__(self, "requested_count", requested_count)
        object.__setattr__(self, "provider", provider)
        object.__setattr__(self, "model", model)
        object.__setattr__(self, "preset", preset)
        object.__setattr__(self, "media_asset_id", media_asset_id)
        object.__setattr__(self, "media_title", media_title)
        object.__setattr__(self, "media_source_url", media_source_url)
        object.__setattr__(self, "media_transcript_pack", media_transcript_pack)


@dataclass(frozen=True)
class MemeRefinementRequest:
    ideation_request: MemeIdeationRequest
    current_generation_summary: str | None = None
    current_candidates: tuple[MemeIdeationCandidate, ...] = ()
    chat_history: tuple[MemeRefinementMessage, ...] = ()
    latest_user_message: str = ""
    debug: bool = False

    def __post_init__(self) -> None:
        current_generation_summary = _clean_optional_text(self.current_generation_summary)
        latest_user_message = _clean_optional_text(self.latest_user_message)
        if latest_user_message is None:
            raise ValueError("latest refinement message is required")
        current_candidates = tuple(self.current_candidates)
        chat_history = tuple(self.chat_history)
        object.__setattr__(self, "current_generation_summary", current_generation_summary)
        object.__setattr__(self, "latest_user_message", latest_user_message)
        object.__setattr__(self, "current_candidates", current_candidates)
        object.__setattr__(self, "chat_history", chat_history)


def _clean_optional_text(value: object | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_tone_hints(value: str | list[str] | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    normalized: list[str] = []
    for item in value:
        text = str(item).strip()
        if text:
            normalized.append(text)
    return normalized


def _normalize_text_items(values: object) -> list[str]:
    if values is None:
        return []
    if isinstance(values, str):
        text = values.strip()
        return [text] if text else []
    normalized: list[str] = []
    for item in values:
        text = _clean_optional_text(item)
        if text:
            normalized.append(text)
    return normalized


def _normalize_media_transcript_pack(value: object | None) -> MediaTranscriptPack | None:
    if value is None:
        return None
    if isinstance(value, MediaTranscriptPack):
        return value
    if isinstance(value, dict):
        return MediaTranscriptPack(
            summary=value.get("summary"),
            key_lines=tuple(_normalize_text_items(value.get("key_lines") or value.get("keyLines"))),
            notable_quotes=tuple(_normalize_text_items(value.get("notable_quotes") or value.get("notableQuotes"))),
            transcript_source=value.get("transcript_source") or value.get("transcriptSource"),
            transcript_excerpt=value.get("transcript_excerpt") or value.get("transcriptExcerpt"),
            tone_cues=tuple(_normalize_text_items(value.get("tone_cues") or value.get("toneCues"))),
        )
    raise ValueError("media_transcript_pack must be an object if provided")


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
        "Generate structured meme ideas for the Instagram page copeharderpls.",
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


def _candidate_from_obj(item: object) -> MemeIdeationCandidate | None:
    if not isinstance(item, dict):
        return None
    direction = _clean_optional_text(item.get("direction"))
    format_name = _clean_optional_text(item.get("format"))
    text = _clean_optional_text(item.get("text"))
    if not direction or not format_name or not text:
        return None
    optional_caption = _clean_optional_text(item.get("optional_caption"))
    notes = _clean_optional_text(item.get("notes"))
    needs_visual_context = bool(item.get("needs_visual_context"))
    return MemeIdeationCandidate(
        direction=direction,
        format=format_name,
        text=text,
        optional_caption=optional_caption,
        needs_visual_context=needs_visual_context,
        notes=notes,
    )


def _extract_json_candidate(raw_text: str) -> str:
    text = raw_text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    start_object = text.find("{")
    end_object = text.rfind("}")
    start_array = text.find("[")
    end_array = text.rfind("]")
    object_candidate = text[start_object : end_object + 1] if start_object != -1 and end_object > start_object else ""
    array_candidate = text[start_array : end_array + 1] if start_array != -1 and end_array > start_array else ""
    if object_candidate and array_candidate:
        return object_candidate if len(object_candidate) >= len(array_candidate) else array_candidate
    return object_candidate or array_candidate or text


def _strip_markdown_fences(raw_text: str) -> str:
    text = raw_text.strip()
    if not text.startswith("```"):
        return text
    lines = text.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def parse_meme_ideation_output(raw_text: str, *, debug: bool) -> MemeIdeationParseResult:
    warnings: list[str] = []
    payload = None
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError:
        try:
            payload = json.loads(_strip_markdown_fences(raw_text))
        except json.JSONDecodeError:
            try:
                payload = json.loads(_extract_json_candidate(raw_text))
                warnings.append("model output required light JSON cleanup before parsing")
            except json.JSONDecodeError:
                raw = raw_text if debug else None
                return MemeIdeationParseResult(
                    candidates=[],
                    warnings=["model output was not valid JSON"],
                    raw_text=raw,
                )

    candidate_rows: object
    if isinstance(payload, dict):
        candidate_rows = payload.get("candidates", [])
    else:
        candidate_rows = payload

    if not isinstance(candidate_rows, list):
        raw = raw_text if debug else None
        return MemeIdeationParseResult(
            candidates=[],
            warnings=["parsed JSON did not contain a candidates array"],
            raw_text=raw,
        )

    candidates: list[MemeIdeationCandidate] = []
    invalid_count = 0
    for item in candidate_rows:
        candidate = _candidate_from_obj(item)
        if candidate is None:
            invalid_count += 1
            continue
        candidates.append(candidate)

    if invalid_count:
        warnings.append(f"ignored {invalid_count} malformed candidate entries")
    if not candidates:
        warnings.append("no valid meme candidates were recovered from model output")

    return MemeIdeationParseResult(
        candidates=candidates,
        warnings=warnings,
        raw_text=raw_text if debug else None,
    )


def parse_meme_refinement_output(raw_text: str, *, debug: bool) -> MemeRefinementParseResult:
    warnings: list[str] = []
    payload = None
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError:
        try:
            payload = json.loads(_strip_markdown_fences(raw_text))
        except json.JSONDecodeError:
            try:
                payload = json.loads(_extract_json_candidate(raw_text))
                warnings.append("model output required light JSON cleanup before parsing")
            except json.JSONDecodeError:
                return MemeRefinementParseResult(
                    assistant_reply="I couldn't turn that refinement pass into structured output, but the model did respond.",
                    suggested_candidates=[],
                    warnings=["model output was not valid JSON"],
                    raw_text=raw_text if debug else None,
                )
    if not isinstance(payload, dict):
        return MemeRefinementParseResult(
            assistant_reply="I couldn't recover a structured refinement response.",
            suggested_candidates=[],
            warnings=["parsed JSON did not contain an object response"],
            raw_text=raw_text if debug else None,
        )
    assistant_reply = _clean_optional_text(payload.get("assistantReply") or payload.get("assistant_reply")) or "Refinement suggestions ready."
    candidate_rows = payload.get("suggestedCandidates") or payload.get("suggested_candidates") or []
    suggested_candidates: list[MemeIdeationCandidate] = []
    invalid_count = 0
    if isinstance(candidate_rows, list):
        for item in candidate_rows:
            candidate = _candidate_from_obj(item)
            if candidate is None:
                invalid_count += 1
                continue
            suggested_candidates.append(candidate)
    elif candidate_rows:
        warnings.append("suggestedCandidates was not a list")
    if invalid_count:
        warnings.append(f"ignored {invalid_count} malformed suggested candidate entries")
    return MemeRefinementParseResult(
        assistant_reply=assistant_reply,
        suggested_candidates=suggested_candidates,
        warnings=warnings,
        raw_text=raw_text if debug else None,
    )


def _score_artifact_shell(candidate: MemeIdeationCandidate, mutation_plan: MutationPlan) -> float:
    haystack = f"{candidate.format} {candidate.direction} {candidate.text} {candidate.notes or ''}".lower()
    score = 0.0
    if candidate.format.lower() in _ARTIFACT_FORMATS:
        score += 1.6
    if candidate.needs_visual_context:
        score += 0.6
    for shell in mutation_plan.artifact_shell_candidates:
        if shell.lower() in haystack:
            score += 0.5
    return min(score, 3.0)


def _score_lexical_novelty(candidate: MemeIdeationCandidate) -> float:
    text = candidate.text
    words = [word.strip(".,:;!?()[]{}\"'").lower() for word in text.split()]
    long_words = sum(1 for word in words if len(word) >= 9)
    weird_words = sum(1 for word in words if "-" in word or any(char.isdigit() for char in word))
    return min(0.4 * long_words + 0.6 * weird_words, 3.0)


def _score_domain_collision(candidate: MemeIdeationCandidate, mutation_plan: MutationPlan) -> float:
    haystack = f"{candidate.direction} {candidate.text} {candidate.notes or ''}".lower()
    score = 0.0
    for domain in mutation_plan.domain_collision_candidates:
        keywords = _DOMAIN_KEYWORDS.get(domain, set())
        if any(keyword in haystack for keyword in keywords):
            score += 1.0
    return min(score, 3.0)


def _score_delayed_recognition(candidate: MemeIdeationCandidate) -> float:
    text = candidate.text
    score = 0.0
    if len(text.split()) >= 8:
        score += 0.8
    if any(char.isdigit() for char in text):
        score += 0.8
    if "/" in text or "before" in text.lower() or "pending" in text.lower():
        score += 0.8
    return min(score, 3.0)


def _score_fake_authority(candidate: MemeIdeationCandidate) -> float:
    haystack = f"{candidate.direction} {candidate.text} {candidate.notes or ''}".lower()
    return min(sum(0.5 for word in _FAKE_AUTHORITY_WORDS if word in haystack), 3.0)


def _score_implied_lore(candidate: MemeIdeationCandidate) -> float:
    haystack = f"{candidate.direction} {candidate.text} {candidate.notes or ''}".lower()
    score = 0.0
    if candidate.notes:
        score += 0.8
    if any(term in haystack for term in ("again", "still", "flagged", "review", "bloodline", "noticed", "committee")):
        score += 1.0
    if candidate.optional_caption:
        score += 0.4
    return min(score, 3.0)


def _score_normie_risk(candidate: MemeIdeationCandidate) -> float:
    haystack = f"{candidate.direction} {candidate.text} {candidate.notes or ''} {candidate.optional_caption or ''}".lower()
    risk = 0.0
    for phrase in _NORMIE_RISK_PHRASES:
        if phrase in haystack:
            risk += 1.1
    if "#" in haystack:
        risk += 2.2
    if len(candidate.text.split()) < 5:
        risk += 0.5
    if candidate.optional_caption and len(candidate.optional_caption.split()) > 8:
        risk += 0.9
    if candidate.optional_caption and any(term in candidate.optional_caption.lower() for term in ("don't forget", "the data doesn't lie", "it's not just", "if you aren't")):
        risk += 0.9
    if candidate.notes and any(term in candidate.notes.lower() for term in ("the core hit", "should look", "the jump from", "the escalation from", "the visual should", "place this text over")):
        risk += 0.9
    if candidate.format.lower().startswith("internal memo"):
        risk += 0.4
    return min(risk, 4.0)


def judge_candidate(candidate: MemeIdeationCandidate, *, candidate_index: int, mutation_plan: MutationPlan) -> JudgeScorecard:
    artifact_shell_strength = _score_artifact_shell(candidate, mutation_plan)
    lexical_novelty = _score_lexical_novelty(candidate)
    domain_collision_strength = _score_domain_collision(candidate, mutation_plan)
    delayed_recognition = _score_delayed_recognition(candidate)
    fake_authority_energy = _score_fake_authority(candidate)
    implied_lore_density = _score_implied_lore(candidate)
    normie_contamination_risk = _score_normie_risk(candidate)
    total_score = (
        artifact_shell_strength
        + lexical_novelty
        + domain_collision_strength
        + delayed_recognition
        + fake_authority_energy
        + implied_lore_density
        - normie_contamination_risk
    )
    warnings: list[str] = []
    if normie_contamination_risk >= 1.4:
        warnings.append("candidate reads too smooth or normie-safe")
    if artifact_shell_strength < 0.8:
        warnings.append("candidate lacks a strong artifact shell")
    accepted = total_score >= 5.6 and normie_contamination_risk < 1.5
    return JudgeScorecard(
        candidate_index=candidate_index,
        artifact_shell_strength=artifact_shell_strength,
        lexical_novelty=lexical_novelty,
        domain_collision_strength=domain_collision_strength,
        delayed_recognition=delayed_recognition,
        fake_authority_energy=fake_authority_energy,
        implied_lore_density=implied_lore_density,
        normie_contamination_risk=normie_contamination_risk,
        total_score=total_score,
        accepted=accepted,
        warnings=tuple(warnings),
    )


def rewrite_candidate_once(candidate: MemeIdeationCandidate, mutation_plan: MutationPlan) -> MemeIdeationCandidate:
    if any(char.isdigit() for char in candidate.text) and any(domain.lower() in candidate.text.lower() for domain in mutation_plan.domain_collision_candidates):
        return candidate
    chosen_domain = mutation_plan.domain_collision_candidates[0] if mutation_plan.domain_collision_candidates else "compliance"
    detail = _REWRITE_DETAILS.get(chosen_domain, f"under {chosen_domain} review")
    if detail.lower() in candidate.text.lower():
        return candidate
    new_text = candidate.text.rstrip(" .")
    separator = " / " if "/" not in new_text else " // "
    new_text = f"{new_text}{separator}{detail}"
    notes = candidate.notes or ""
    extra_note = f"rewritten once to increase domain collision via {chosen_domain}"
    merged_notes = f"{notes}; {extra_note}".strip("; ")
    return replace(candidate, text=new_text, notes=merged_notes)


async def _resolve_model(provider: Provider, requested_model: str | None) -> str:
    if requested_model:
        return requested_model
    models = await provider.list_models()
    for model in models:
        if model.kind == "chat":
            return model.id
    raise ValueError("provider has no chat-capable models available")


async def _run_provider_text(*, provider: Provider, prompt: str, model: str, system_prompt: str) -> str:
    abort_event = asyncio.Event()
    chunks: list[str] = []
    async for event in provider.run(
        prompt=prompt,
        provider_session_id=None,
        abort_event=abort_event,
        model=model,
        system_prompt=system_prompt,
    ):
        if event.kind == "delta" and event.text:
            chunks.append(event.text)
    return "".join(chunks).strip()


def _judge_candidates(
    candidates: list[MemeIdeationCandidate],
    *,
    mutation_plan: MutationPlan,
    requested_count: int,
) -> tuple[list[MemeIdeationCandidate], list[JudgeScorecard], list[str]]:
    scorecards: list[JudgeScorecard] = []
    accepted: list[tuple[JudgeScorecard, MemeIdeationCandidate]] = []
    borderline: list[tuple[JudgeScorecard, MemeIdeationCandidate]] = []
    warnings: list[str] = []
    for index, candidate in enumerate(candidates):
        scorecard = judge_candidate(candidate, candidate_index=index, mutation_plan=mutation_plan)
        scorecards.append(scorecard)
        if scorecard.accepted:
            accepted.append((scorecard, candidate))
            continue
        if scorecard.total_score >= 4.6 and scorecard.normie_contamination_risk < 2.0:
            rewritten = rewrite_candidate_once(candidate, mutation_plan)
            rewritten_scorecard = judge_candidate(rewritten, candidate_index=index, mutation_plan=mutation_plan)
            scorecards.append(rewritten_scorecard)
            if rewritten_scorecard.accepted:
                accepted.append((rewritten_scorecard, rewritten))
            else:
                borderline.append((rewritten_scorecard, rewritten))
        else:
            borderline.append((scorecard, candidate))

    accepted.sort(key=lambda item: item[0].total_score, reverse=True)
    survivors = [candidate for _, candidate in accepted[:requested_count]]
    if not survivors and borderline:
        borderline.sort(key=lambda item: item[0].total_score, reverse=True)
        top_scorecard, top_candidate = borderline[0]
        if top_scorecard.total_score >= 6.8 and top_scorecard.normie_contamination_risk <= 1.9:
            survivors = [top_candidate]
            warnings.append("judge escalated one borderline candidate to avoid an empty result set")
    if len(survivors) < requested_count:
        warnings.append(f"judge only found {len(survivors)} candidates above the anti-mid threshold")
    return survivors, scorecards, warnings


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


async def ideate_memes(
    *,
    provider_name: str,
    provider: Provider,
    request: MemeIdeationRequest,
) -> MemeIdeationResponse:
    if provider_name not in _LOCAL_PROVIDER_IDS:
        raise ValueError(f"provider {provider_name} is not a supported local meme ideation provider")

    knowledge_context = build_meme_knowledge_index()
    knowledge_pack = build_meme_knowledge_pack(
        knowledge_context,
        topic=request.topic,
        trend_summary=request.trend_summary,
        image_springboard=request.image_springboard,
        tone_hints=request.tone_hints,
    )
    mutation_plan = build_mutation_plan(request, knowledge_pack)
    system_prompt = build_meme_system_prompt(request, knowledge_pack=knowledge_pack, mutation_plan=mutation_plan)
    user_prompt = build_meme_user_prompt(request, knowledge_pack=knowledge_pack, mutation_plan=mutation_plan)
    resolved_model = await _resolve_model(provider, request.model)

    raw_text = await _run_provider_text(provider=provider, prompt=user_prompt, model=resolved_model, system_prompt=system_prompt)
    parsed = parse_meme_ideation_output(raw_text, debug=request.debug)
    survivors, scorecards, judge_warnings = _judge_candidates(
        parsed.candidates,
        mutation_plan=mutation_plan,
        requested_count=request.requested_count,
    )
    warnings = list(knowledge_pack.warnings) + parsed.warnings
    if parsed.candidates and not survivors:
        warnings.append("generation succeeded but every candidate was rejected as too mid")
    if request.debug and scorecards:
        judge_warnings.extend(
            f"candidate {scorecard.candidate_index}: total={scorecard.total_score:.2f}, normieRisk={scorecard.normie_contamination_risk:.2f}, accepted={scorecard.accepted}"
            for scorecard in scorecards[: request.requested_count]
        )
    return MemeIdeationResponse(
        candidates=survivors,
        provider=provider_name,
        model=resolved_model,
        preset=request.preset,
        schema_version=MEME_IDEATION_SCHEMA_VERSION,
        prompt_version=MEME_IDEATION_PROMPT_VERSION,
        warnings=warnings,
        raw_text=parsed.raw_text,
        knowledge_pack_version=knowledge_pack.version,
        judge_warnings=judge_warnings,
        artifact_shell=mutation_plan.artifact_shell_candidates[0] if mutation_plan.artifact_shell_candidates else None,
        mutation_notes=list(mutation_plan.mutation_notes),
    )


async def refine_memes(
    *,
    provider_name: str,
    provider: Provider,
    request: MemeRefinementRequest,
) -> MemeRefinementResponse:
    if provider_name not in _LOCAL_PROVIDER_IDS:
        raise ValueError(f"provider {provider_name} is not a supported local meme ideation provider")

    ideation_request = request.ideation_request
    knowledge_context = build_meme_knowledge_index()
    knowledge_pack = build_meme_knowledge_pack(
        knowledge_context,
        topic=ideation_request.topic,
        trend_summary=ideation_request.trend_summary,
        image_springboard=ideation_request.image_springboard,
        tone_hints=ideation_request.tone_hints,
    )
    mutation_plan = build_mutation_plan(ideation_request, knowledge_pack)
    system_prompt = build_meme_refinement_system_prompt(request, knowledge_pack=knowledge_pack, mutation_plan=mutation_plan)
    user_prompt = build_meme_refinement_user_prompt(request, knowledge_pack=knowledge_pack, mutation_plan=mutation_plan)
    resolved_model = await _resolve_model(provider, ideation_request.model)

    raw_text = await _run_provider_text(provider=provider, prompt=user_prompt, model=resolved_model, system_prompt=system_prompt)
    parsed = parse_meme_refinement_output(raw_text, debug=request.debug)
    survivors, scorecards, judge_warnings = _judge_candidates(
        parsed.suggested_candidates,
        mutation_plan=mutation_plan,
        requested_count=min(max(1, len(request.current_candidates) or 1), _MAX_REQUESTED_COUNT),
    )
    warnings = list(knowledge_pack.warnings) + parsed.warnings
    if parsed.suggested_candidates and not survivors:
        warnings.append("refinement produced candidates, but every rewrite was rejected as too mid")
    if request.debug and scorecards:
        judge_warnings.extend(
            f"candidate {scorecard.candidate_index}: total={scorecard.total_score:.2f}, normieRisk={scorecard.normie_contamination_risk:.2f}, accepted={scorecard.accepted}"
            for scorecard in scorecards[: max(1, len(request.current_candidates))]
        )
    return MemeRefinementResponse(
        assistant_reply=parsed.assistant_reply,
        suggested_candidates=survivors,
        provider=provider_name,
        model=resolved_model,
        preset=ideation_request.preset,
        schema_version=MEME_IDEATION_SCHEMA_VERSION,
        prompt_version=MEME_IDEATION_PROMPT_VERSION,
        warnings=warnings,
        raw_text=parsed.raw_text,
        knowledge_pack_version=knowledge_pack.version,
        judge_warnings=judge_warnings,
        artifact_shell=mutation_plan.artifact_shell_candidates[0] if mutation_plan.artifact_shell_candidates else None,
        mutation_notes=list(mutation_plan.mutation_notes),
    )
