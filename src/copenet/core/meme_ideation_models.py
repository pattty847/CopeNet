"""Data models and normalization helpers for meme ideation."""

from __future__ import annotations

from dataclasses import dataclass, field

from .meme_ideation_constants import MEME_IDEATION_PRESET_ID, _MAX_REQUESTED_COUNT


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
