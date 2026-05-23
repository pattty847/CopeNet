"""Capability normalization for the CopeNet chat harness."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ModelCapabilityProfile:
    """Normalized model/provider capability flags."""

    provider: str
    model: str | None
    chat: bool = True
    embeddings: bool = False
    tool_calls: bool = False
    streaming: bool = True
    resume: bool = False
    prompted_tool_use: bool = False
    # Phase 2 (HARNESS_REBUILD_V2): provider speaks the native Responses API
    # (streaming function_call lifecycle + function_call_output replay).
    responses_api: bool = False


def normalize_capabilities(provider_meta: dict[str, Any]) -> dict[str, bool]:
    """Normalize loose provider capability metadata into one canonical shape."""
    raw = provider_meta.get("capabilities")
    if not isinstance(raw, dict):
        return {}
    return {
        "chat": bool(raw.get("chat", True)),
        "embeddings": bool(raw.get("embeddings", False)),
        "toolCalls": bool(raw.get("toolCalls", False)),
        "streaming": bool(raw.get("streaming", True)),
        "resume": bool(raw.get("resume", False)),
        "promptedToolUse": bool(raw.get("promptedToolUse", raw.get("toolCalls", False))),
        "responsesApi": bool(raw.get("responsesApi", False)),
    }
