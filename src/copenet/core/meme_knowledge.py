from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from copenet.core.knowledge_runtime import (
    KnowledgeDocument,
    KnowledgeExcerpt,
    KnowledgePack,
    KnowledgeSection,
    extract_markdown_sections,
    stable_id,
    summarize_text,
    tokenize,
    write_document_index,
)

DEFAULT_MEME_LIBRARY_ROOT = Path("/Users/copeharder/Documents/Obsidian/Sable Brain/05 Research/Meme Style Library")
MEME_KNOWLEDGE_PACK_VERSION = "meme-kb-v1"
MEME_INDEX_FILENAME = "meme_style_library_index.json"

_ARTIFACT_FORMAT_HINTS = (
    "receipt",
    "fortune cookie",
    "sticky note",
    "job listing",
    "product label",
    "quote card",
    "image overlay",
    "comment screenshot",
    "protest sign",
)

_SUBCULTURE_HINTS = {
    "mogging",
    "looksmaxx",
    "looksmaxxing",
    "cortisol",
    "clavicular",
    "low",
    "t",
    "aura",
    "posture",
    "maxxing",
    "phenotype",
}

_DOC_TYPE_BY_NAME = {
    "voice map": "voice_map",
    "humor mechanisms": "humor_mechanism",
    "meme engines": "meme_engine",
    "caption pattern bank": "caption_pattern",
    "human nuance capture": "nuance_note",
    "topical memeifier": "topical_workflow",
    "subculture lexicon - looksmaxxing mogging": "lexicon_note",
    "subculture lexicon dataset spec": "lexicon_note",
    "meme ideation prompt v2 design": "prompt_design_note",
    "prompt iteration log": "feedback_rule",
    "curated model test payloads": "prompt_design_note",
}


@dataclass(frozen=True)
class MemeKnowledgePack(KnowledgePack):
    voice_summary: tuple[KnowledgeExcerpt, ...] = ()
    anti_patterns: tuple[KnowledgeExcerpt, ...] = ()
    engine_pack: tuple[KnowledgeExcerpt, ...] = ()
    mechanism_pack: tuple[KnowledgeExcerpt, ...] = ()
    caption_pattern_pack: tuple[KnowledgeExcerpt, ...] = ()
    nuance_pack: tuple[KnowledgeExcerpt, ...] = ()
    case_study_pack: tuple[KnowledgeExcerpt, ...] = ()
    feedback_pack: tuple[KnowledgeExcerpt, ...] = ()
    lexicon_pack: tuple[KnowledgeExcerpt, ...] = ()
    artifact_shell_pack: tuple[str, ...] = ()


@dataclass(frozen=True)
class MemeKnowledgeContext:
    root_dir: Path
    cache_path: Path
    documents: tuple[KnowledgeDocument, ...]
    warnings: tuple[str, ...] = ()


def resolve_meme_library_root() -> Path:
    override = os.environ.get("COPNET_MEME_KB_ROOT", "").strip()
    return Path(override).expanduser() if override else DEFAULT_MEME_LIBRARY_ROOT


def resolve_meme_library_cache_path() -> Path:
    override = os.environ.get("COPNET_MEME_KB_CACHE_DIR", "").strip()
    if override:
        return Path(override).expanduser() / MEME_INDEX_FILENAME
    workdir = Path(os.environ.get("COPNET_WORKDIR") or os.getcwd()).resolve()
    return workdir / "knowledge-cache" / MEME_INDEX_FILENAME


def _doc_type_for_path(path: Path) -> str:
    name = path.stem.strip().lower()
    if path.parent.name.lower() == "case studies":
        return "case_study"
    if path.parent.name.lower() == "feedback":
        return "feedback_rule"
    return _DOC_TYPE_BY_NAME.get(name, "note")


def _title_from_text(path: Path, text: str) -> str:
    first_line = text.strip().splitlines()[0].strip() if text.strip() else path.stem
    if first_line.startswith("# "):
        return first_line[2:].strip()
    return path.stem


def _tag_document(path: Path, text: str, doc_type: str) -> tuple[str, ...]:
    tags = set(tokenize(path.stem.replace("_", " ")))
    lowered = text.lower()
    if any(hint in lowered for hint in _SUBCULTURE_HINTS):
        tags.add("subculture")
    if any(hint in lowered for hint in ("artifact", "format", "sticky note", "fortune cookie", "receipt")):
        tags.add("artifact")
    if "politic" in lowered or "institution" in lowered or "corporate" in lowered:
        tags.add("institutional")
    if "sports" in lowered or "commentary" in lowered:
        tags.add("cadence")
    tags.add(doc_type)
    return tuple(sorted(tags))


def build_meme_knowledge_index(root_dir: Path | None = None, cache_path: Path | None = None) -> MemeKnowledgeContext:
    root = (root_dir or resolve_meme_library_root()).expanduser()
    resolved_cache = cache_path or resolve_meme_library_cache_path()
    if not root.exists():
        return MemeKnowledgeContext(root_dir=root, cache_path=resolved_cache, documents=(), warnings=(f"meme knowledge base not found: {root}",))

    documents: list[KnowledgeDocument] = []
    for path in sorted(root.rglob("*.md")):
        text = path.read_text(encoding="utf-8")
        doc_type = _doc_type_for_path(path)
        title = _title_from_text(path, text)
        sections: list[KnowledgeSection] = []
        for section_title, body in extract_markdown_sections(text):
            sections.append(
                KnowledgeSection(
                    section_title=section_title,
                    text=body,
                    summary=summarize_text(body),
                    tags=_tag_document(path, body, doc_type),
                )
            )
        summary = summarize_text(text)
        document = KnowledgeDocument(
            id=stable_id(str(path.relative_to(root)), str(path.stat().st_mtime)),
            doc_type=doc_type,
            title=title,
            source_path=str(path),
            tags=_tag_document(path, text, doc_type),
            text=text.strip(),
            summary=summary,
            section_title="Overview",
            last_modified=path.stat().st_mtime,
            sections=tuple(sections),
        )
        documents.append(document)
    write_document_index(documents, resolved_cache)
    return MemeKnowledgeContext(root_dir=root, cache_path=resolved_cache, documents=tuple(documents))


def _score_excerpt(excerpt: KnowledgeExcerpt, query_tokens: set[str], *, topical: bool, image_shell: bool, subculture: bool, cadence: bool) -> int:
    haystack = " ".join((excerpt.title, excerpt.section_title, excerpt.text, " ".join(excerpt.tags))).lower()
    score = 0
    score += sum(5 for token in query_tokens if token in haystack)
    if topical and ("topical" in haystack or "politic" in haystack or "institution" in haystack):
        score += 7
    if image_shell and ("image" in haystack or "format" in haystack or "artifact" in haystack or "shell" in haystack):
        score += 7
    if subculture and ("subculture" in haystack or "mog" in haystack or "maxx" in haystack or "cortisol" in haystack):
        score += 7
    if cadence and ("cadence" in haystack or "sports" in haystack or "commentary" in haystack or "gibberish" in haystack):
        score += 7
    return score


def _excerpt(document: KnowledgeDocument, section: KnowledgeSection | None = None) -> KnowledgeExcerpt:
    if section is None:
        return KnowledgeExcerpt(
            document_id=document.id,
            doc_type=document.doc_type,
            title=document.title,
            source_path=document.source_path,
            section_title=document.section_title,
            text=document.text,
            summary=document.summary,
            tags=document.tags,
        )
    return KnowledgeExcerpt(
        document_id=document.id,
        doc_type=document.doc_type,
        title=document.title,
        source_path=document.source_path,
        section_title=section.section_title,
        text=section.text,
        summary=section.summary,
        tags=section.tags,
    )


def _pick_top(documents: tuple[KnowledgeDocument, ...], *, doc_types: set[str], query_tokens: set[str], limit: int, topical: bool, image_shell: bool, subculture: bool, cadence: bool) -> tuple[KnowledgeExcerpt, ...]:
    scored: list[tuple[int, KnowledgeExcerpt]] = []
    for document in documents:
        if document.doc_type not in doc_types:
            continue
        if document.sections:
            for section in document.sections:
                excerpt = _excerpt(document, section)
                score = _score_excerpt(excerpt, query_tokens, topical=topical, image_shell=image_shell, subculture=subculture, cadence=cadence)
                scored.append((score, excerpt))
        else:
            excerpt = _excerpt(document)
            score = _score_excerpt(excerpt, query_tokens, topical=topical, image_shell=image_shell, subculture=subculture, cadence=cadence)
            scored.append((score, excerpt))
    scored.sort(key=lambda item: (-item[0], item[1].title, item[1].section_title))
    out: list[KnowledgeExcerpt] = []
    seen: set[tuple[str, str]] = set()
    for _, excerpt in scored:
        key = (excerpt.document_id, excerpt.section_title)
        if key in seen:
            continue
        seen.add(key)
        out.append(excerpt)
        if len(out) >= limit:
            break
    return tuple(out)


def _artifact_shell_pack(image_shell: bool, topical: bool, cadence: bool) -> tuple[str, ...]:
    shells = list(_ARTIFACT_FORMAT_HINTS)
    if topical:
        shells[:0] = ["internal memo", "policy notice", "press quote"]
    if image_shell:
        shells[:0] = ["reaction image overlay", "screenshot annotation"]
    if cadence:
        shells[:0] = ["fake commentary graphic", "ticker chyron"]
    unique: list[str] = []
    for shell in shells:
        if shell not in unique:
            unique.append(shell)
    return tuple(unique[:6])


def build_meme_knowledge_pack(
    context: MemeKnowledgeContext,
    *,
    topic: str | None,
    trend_summary: str | None,
    image_springboard: str | None,
    tone_hints: tuple[str, ...] | list[str] | None,
) -> MemeKnowledgePack:
    query_tokens = set(tokenize(" ".join(filter(None, [topic or "", trend_summary or "", image_springboard or "", " ".join(tone_hints or [])]))))
    topical = bool(trend_summary and trend_summary.strip())
    image_shell = bool(image_springboard and image_springboard.strip())
    subculture = bool(query_tokens & _SUBCULTURE_HINTS) or any(hint in {"copecore", "edgy", "raw"} for hint in (tone_hints or []))
    cadence = any(token in query_tokens for token in {"sports", "commentary", "gibberish", "cadence", "ticker", "analyst"})

    voice_summary = _pick_top(context.documents, doc_types={"voice_map"}, query_tokens=query_tokens, limit=1, topical=topical, image_shell=image_shell, subculture=subculture, cadence=cadence)
    mechanism_pack = _pick_top(context.documents, doc_types={"humor_mechanism"}, query_tokens=query_tokens, limit=2, topical=topical, image_shell=image_shell, subculture=subculture, cadence=cadence)
    engine_pack = _pick_top(context.documents, doc_types={"meme_engine", "topical_workflow"}, query_tokens=query_tokens, limit=1, topical=topical, image_shell=image_shell, subculture=subculture, cadence=cadence)
    caption_pattern_pack = _pick_top(context.documents, doc_types={"caption_pattern"}, query_tokens=query_tokens, limit=1, topical=topical, image_shell=image_shell, subculture=subculture, cadence=cadence)
    nuance_pack = _pick_top(context.documents, doc_types={"nuance_note"}, query_tokens=query_tokens, limit=1, topical=topical, image_shell=image_shell, subculture=subculture, cadence=cadence)
    case_study_pack = _pick_top(context.documents, doc_types={"case_study"}, query_tokens=query_tokens, limit=3, topical=topical, image_shell=image_shell, subculture=subculture, cadence=cadence)
    feedback_pack = _pick_top(context.documents, doc_types={"feedback_rule"}, query_tokens=query_tokens, limit=1, topical=topical, image_shell=image_shell, subculture=subculture, cadence=cadence)
    lexicon_pack = _pick_top(context.documents, doc_types={"lexicon_note"}, query_tokens=query_tokens, limit=1 if subculture else 0, topical=topical, image_shell=image_shell, subculture=subculture, cadence=cadence)

    anti_patterns: list[KnowledgeExcerpt] = []
    if voice_summary:
        anti_patterns.append(voice_summary[0])
    if feedback_pack:
        anti_patterns.extend(feedback_pack[:1])

    excerpts = tuple(
        list(voice_summary)
        + list(mechanism_pack)
        + list(engine_pack)
        + list(caption_pattern_pack)
        + list(nuance_pack)
        + list(case_study_pack)
        + list(feedback_pack)
        + list(lexicon_pack)
    )

    return MemeKnowledgePack(
        version=MEME_KNOWLEDGE_PACK_VERSION,
        warnings=context.warnings,
        excerpts=excerpts,
        voice_summary=voice_summary,
        anti_patterns=tuple(anti_patterns),
        engine_pack=engine_pack,
        mechanism_pack=mechanism_pack,
        caption_pattern_pack=caption_pattern_pack,
        nuance_pack=nuance_pack,
        case_study_pack=case_study_pack,
        feedback_pack=feedback_pack,
        lexicon_pack=lexicon_pack,
        artifact_shell_pack=_artifact_shell_pack(image_shell, topical, cadence),
    )
