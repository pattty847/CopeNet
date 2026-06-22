"""Persona flavor draft parsing helpers."""

from __future__ import annotations

import json


def parse_persona_flavor_draft(raw_text: str) -> dict:
    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        parsed = {}
    if not isinstance(parsed, dict):
        parsed = {}
    return {
        "displayName": str(parsed.get("displayName") or parsed.get("name") or "Model Flavor").strip(),
        "identityMarkdown": str(parsed.get("identityMarkdown") or parsed.get("identity") or raw_text or "# Model Flavor").strip(),
        "soulMarkdown": str(parsed.get("soulMarkdown") or parsed.get("soul") or "").strip(),
        "notesMarkdown": str(parsed.get("notesMarkdown") or parsed.get("notes") or "").strip(),
    }
