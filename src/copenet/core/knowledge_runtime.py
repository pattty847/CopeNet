from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
_WORD_RE = re.compile(r"[a-z0-9][a-z0-9-]+", re.IGNORECASE)


@dataclass(frozen=True)
class KnowledgeTag:
    value: str


@dataclass(frozen=True)
class KnowledgeSection:
    section_title: str
    text: str
    summary: str
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class KnowledgeDocument:
    id: str
    doc_type: str
    title: str
    source_path: str
    tags: tuple[str, ...]
    text: str
    summary: str
    section_title: str
    last_modified: float
    sections: tuple[KnowledgeSection, ...] = ()


@dataclass(frozen=True)
class KnowledgeExcerpt:
    document_id: str
    doc_type: str
    title: str
    source_path: str
    section_title: str
    text: str
    summary: str
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class KnowledgePack:
    version: str
    warnings: tuple[str, ...] = ()
    excerpts: tuple[KnowledgeExcerpt, ...] = ()


def stable_id(*parts: str) -> str:
    raw = "::".join(parts).encode("utf-8")
    return hashlib.sha1(raw).hexdigest()[:16]


def tokenize(value: str) -> list[str]:
    return [match.group(0).lower() for match in _WORD_RE.finditer(value)]


def summarize_text(text: str, *, max_words: int = 36) -> str:
    cleaned = " ".join(text.split())
    if not cleaned:
        return ""
    words = cleaned.split(" ")
    if len(words) <= max_words:
        return cleaned
    return " ".join(words[:max_words]).rstrip(",;:-") + "..."


def extract_markdown_sections(text: str) -> list[tuple[str, str]]:
    lines = text.splitlines()
    sections: list[tuple[str, list[str]]] = []
    current_title = "Overview"
    current_lines: list[str] = []
    for line in lines:
        heading = _HEADING_RE.match(line)
        if heading:
            if current_lines:
                sections.append((current_title, current_lines))
            current_title = heading.group(2).strip()
            current_lines = []
            continue
        current_lines.append(line)
    if current_lines:
        sections.append((current_title, current_lines))

    out: list[tuple[str, str]] = []
    for title, body_lines in sections:
        body = "\n".join(body_lines).strip()
        if body:
            out.append((title, body))
    return out


def serialize_documents(documents: Iterable[KnowledgeDocument]) -> list[dict[str, object]]:
    payload: list[dict[str, object]] = []
    for document in documents:
        item = asdict(document)
        payload.append(item)
    return payload


def write_document_index(documents: Iterable[KnowledgeDocument], target_path: Path) -> None:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    payload = serialize_documents(documents)
    tmp_path = target_path.with_suffix(target_path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(target_path)
