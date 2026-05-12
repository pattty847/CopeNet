"""Selection, extraction, and prompt payloads for user-visible memory."""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from copenet.core.sessions.session_store import utc_now_iso

from .store import MemoryCategory, MemoryRecord, MemoryStore

if TYPE_CHECKING:
    from copenet.core.runtime import RunRecord

_STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "your", "you", "about", "into", "like", "have", "want",
    "what", "when", "where", "should", "would", "could", "just", "really", "make", "feel", "need", "more", "less",
    "because", "there", "their", "them", "then", "than", "been", "will", "keep", "our", "ours", "its",
}
_SENSITIVE_PATTERNS = [
    r"\bpassword\b",
    r"\bapi\s*key\b",
    r"\bsecret\b",
    r"\btoken\b",
    r"\boauth\b",
    r"\brefresh\s*token\b",
    r"\baccess\s*token\b",
    r"\bssn\b",
    r"\bsocial security\b",
    r"\bcredit card\b",
    r"\bprivate key\b",
]


@dataclass(frozen=True)
class MemoryPromptPayload:
    memory_items: list[MemoryRecord] = field(default_factory=list)
    digest: str | None = None

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "items": [item.to_public_dict() for item in self.memory_items],
            "digest": self.digest,
            "count": len(self.memory_items),
        }


@dataclass(frozen=True)
class MemoryExtractionResult:
    created: list[MemoryRecord] = field(default_factory=list)


class MemoryService:
    def __init__(self, store: MemoryStore) -> None:
        self._store = store

    def list_memory(self, *, include_archived: bool = False, category: MemoryCategory | None = None, limit: int = 50) -> list[MemoryRecord]:
        rows = self._store.list_items(include_archived=include_archived)
        if category:
            rows = [item for item in rows if item.category == category]
        return rows[:max(1, limit)]

    def upsert_memory(
        self,
        *,
        category: MemoryCategory,
        title: str,
        summary: str,
        detail: str | None = None,
        tags: list[str] | tuple[str, ...] | None = None,
        source: str = "explicit",
        confidence: float = 0.8,
        memory_id: str | None = None,
        last_session_key: str | None = None,
        archived: bool = False,
    ) -> MemoryRecord:
        now = utc_now_iso()
        existing = self._store.get(memory_id or "") if memory_id else self._find_duplicate(category=category, title=title, summary=summary)
        record = MemoryRecord(
            id=(existing.id if existing is not None else (memory_id or f"memory-{uuid4()}")),
            category=category,
            title=title.strip() or "Memory",
            summary=summary.strip() or title.strip() or "Memory item",
            detail=(detail or "").strip() or None,
            tags=tuple(sorted({tag.strip() for tag in (tags or []) if str(tag).strip()})),
            source=source,
            confidence=max(0.0, min(1.0, confidence)),
            created_at=existing.created_at if existing is not None else now,
            updated_at=now,
            archived=archived,
            last_session_key=last_session_key or (existing.last_session_key if existing is not None else None),
        )
        return self._store.upsert(record)

    def archive_memory(self, memory_id: str, *, archived: bool = True) -> MemoryRecord | None:
        return self._store.archive(memory_id, archived=archived)

    def build_prompt_payload(
        self,
        *,
        query: str,
        limit: int = 3,
    ) -> MemoryPromptPayload:
        rows = self.select_relevant(query=query, limit=limit)
        if not rows:
            return MemoryPromptPayload()
        digest_lines = ["Relevant memory:"]
        for item in rows:
            digest_lines.append(f"- [{item.category}] {item.title}: {item.summary}")
        return MemoryPromptPayload(memory_items=rows, digest="\n".join(digest_lines))

    def select_relevant(self, *, query: str, limit: int = 3) -> list[MemoryRecord]:
        rows = self._store.list_items(include_archived=False)
        if not rows:
            return []
        query_terms = _terms(query)
        ranked: list[tuple[int, MemoryRecord]] = []
        for item in rows:
            score = 0
            haystack = " ".join([item.title, item.summary, item.detail or "", " ".join(item.tags)]).lower()
            item_terms = _terms(haystack)
            overlap = len(query_terms & item_terms)
            score += overlap * 3
            if item.category == "ongoing_priority":
                score += 3
            elif item.category == "project_convention":
                score += 2
            if any(term in haystack for term in query_terms):
                score += 1
            if score > 0:
                ranked.append((score, item))
        ranked.sort(key=lambda pair: (pair[0], pair[1].updated_at), reverse=True)
        if ranked:
            return [item for _, item in ranked[:limit]]
        return rows[:min(limit, len(rows))]

    def extract_from_run(self, *, user_message: str, run_record: "RunRecord") -> MemoryExtractionResult:
        text = user_message.strip()
        if not text or _looks_sensitive(text):
            return MemoryExtractionResult()
        created: list[MemoryRecord] = []
        lower = text.lower()
        if any(phrase in lower for phrase in ["i like", "i love", "prefer", "i want", "keep it", "make it feel"]):
            summary = _clip_sentence(text)
            created.append(
                self.upsert_memory(
                    category="preference",
                    title="Operator preference",
                    summary=summary,
                    detail=text,
                    tags=["operator", "preference"],
                    source="session_observation",
                    confidence=0.78,
                    last_session_key=run_record.session_key,
                )
            )
        if any(phrase in lower for phrase in ["we should", "our goal", "the goal", "north star", "friend first", "workshop"]):
            summary = _clip_sentence(text)
            created.append(
                self.upsert_memory(
                    category="ongoing_priority",
                    title="Current CopeNet direction",
                    summary=summary,
                    detail=text,
                    tags=["copenet", "direction"],
                    source="session_observation",
                    confidence=0.82,
                    last_session_key=run_record.session_key,
                )
            )
        if any(phrase in lower for phrase in ["we always", "keep the theme", "do not", "should stay", "naming", "session semantics"]):
            summary = _clip_sentence(text)
            created.append(
                self.upsert_memory(
                    category="project_convention",
                    title="Working convention",
                    summary=summary,
                    detail=text,
                    tags=["workflow", "convention"],
                    source="session_observation",
                    confidence=0.76,
                    last_session_key=run_record.session_key,
                )
            )
        unique: dict[str, MemoryRecord] = {item.id: item for item in created}
        return MemoryExtractionResult(created=list(unique.values()))

    def _find_duplicate(self, *, category: MemoryCategory, title: str, summary: str) -> MemoryRecord | None:
        normalized_title = _normalize_dedupe(title)
        normalized_summary = _normalize_dedupe(summary)
        for item in self._store.list_items(include_archived=True):
            if item.category != category:
                continue
            if _normalize_dedupe(item.summary) == normalized_summary:
                return item
            if normalized_title and _normalize_dedupe(item.title) == normalized_title:
                return item
        return None


def _normalize_dedupe(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _terms(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-zA-Z0-9_:-]{3,}", (text or "").lower()) if token not in _STOPWORDS}


def _looks_sensitive(text: str) -> bool:
    lowered = text.lower()
    return any(re.search(pattern, lowered) for pattern in _SENSITIVE_PATTERNS)


def _clip_sentence(text: str, limit: int = 180) -> str:
    value = re.sub(r"\s+", " ", text.strip())
    if len(value) <= limit:
        return value
    clipped = value[:limit].rsplit(" ", 1)[0].strip()
    return f"{clipped}…" if clipped else value[:limit]
