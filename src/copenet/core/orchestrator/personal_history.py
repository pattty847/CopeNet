"""Personal-history helpers for quiet sessions inside Agents."""

from __future__ import annotations

import re


PERSONAL_STARTER_TAGS: dict[str, list[str]] = {
    "think_through_something": ["thinking", "clarity"],
    "plan_my_next_steps": ["planning", "execution"],
    "reflect_and_organize": ["reflection", "organization"],
}

_QUESTION_LINE_RE = re.compile(r"[-*]\s*(.+\?)\s*$")
_QUESTION_SENTENCE_RE = re.compile(r"([^?]{4,220}\?)")
_DECISION_LINE_RE = re.compile(r"[-*]\s+(.+)")


def normalize_starter_intent(value: str | None) -> str | None:
    text = str(value or "").strip()
    return text if text in PERSONAL_STARTER_TAGS else None


def starter_intent_tags(intent: str | None) -> list[str]:
    normalized = normalize_starter_intent(intent)
    return list(PERSONAL_STARTER_TAGS.get(normalized or "", []))


def normalize_personal_focus(message: str, *, limit: int = 180) -> str:
    compact = " ".join(str(message or "").split())
    if len(compact) <= limit:
        return compact
    return f"{compact[: limit - 1].rstrip()}…"


def extract_personal_questions(*texts: str | None) -> list[str]:
    rows: list[str] = []
    for text in texts:
        if not text:
            continue
        for line in str(text).splitlines():
            match = _QUESTION_LINE_RE.search(line.strip())
            if match:
                _push_unique(rows, match.group(1).strip())
        for match in _QUESTION_SENTENCE_RE.finditer(str(text)):
            candidate = " ".join(match.group(1).split()).strip()
            if candidate:
                _push_unique(rows, candidate)
    return rows[:6]


def extract_resume_decisions(text: str | None) -> list[str]:
    if not text:
        return []
    rows: list[str] = []
    capture = False
    for raw_line in str(text).splitlines():
        line = raw_line.strip()
        if not line:
            if capture:
                break
            continue
        lowered = line.lower().rstrip(":")
        if lowered in {"key decisions", "decisions", "latest decisions", "next steps"}:
            capture = True
            continue
        if line.lower().startswith("decision:"):
            _push_unique(rows, line.split(":", 1)[1].strip())
            continue
        if capture:
            bullet = _DECISION_LINE_RE.match(line)
            if bullet:
                _push_unique(rows, bullet.group(1).strip())
                continue
            if ":" in line and not line.startswith(("http://", "https://")):
                break
    return rows[:5]


def _push_unique(rows: list[str], value: str) -> None:
    text = str(value or "").strip()
    if text and text not in rows:
        rows.append(text)
