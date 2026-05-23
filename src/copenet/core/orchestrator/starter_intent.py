"""Starter-intent normalization for personal "quiet session" creation.

Extracted from the deleted personal_history.py (HARNESS_REBUILD_V2 Phase 1).
personal_history.py was deleted because its keyword-extraction functions
(normalize_personal_focus / extract_personal_questions / extract_resume_decisions)
were the source of the synthetic session-state auto-mutation the rebuild kills.

These two helpers are different: they normalize a user-selected starter intent
chosen explicitly at session-creation time — a real signal, not scraped from
conversation text. They live here so catalog.py can keep seeding starter intent.
"""

from __future__ import annotations


PERSONAL_STARTER_TAGS: dict[str, list[str]] = {
    "think_through_something": ["thinking", "clarity"],
    "plan_my_next_steps": ["planning", "execution"],
    "reflect_and_organize": ["reflection", "organization"],
}


def normalize_starter_intent(value: str | None) -> str | None:
    text = str(value or "").strip()
    return text if text in PERSONAL_STARTER_TAGS else None


def starter_intent_tags(intent: str | None) -> list[str]:
    normalized = normalize_starter_intent(intent)
    return list(PERSONAL_STARTER_TAGS.get(normalized or "", []))
