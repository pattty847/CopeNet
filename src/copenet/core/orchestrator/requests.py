"""Canonical normalized chat request contracts for all transports."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable, Literal
from copenet.core.persona import PersonaPrivacyTier

ChatEmit = Callable[[dict], Awaitable[None]]
SideEventEmit = Callable[[str, dict], Awaitable[None]]


@dataclass(frozen=True)
class MarketContextRequest:
    """Validated chart evidence and annotation authority for one invocation."""

    observation_id: str
    document_id: str
    view_id: str
    detail: Literal["quick", "balanced", "deep"] = "balanced"
    access: Literal["read", "annotate"] = "read"

    @classmethod
    def from_dict(cls, raw: object) -> "MarketContextRequest":
        if not isinstance(raw, dict) or set(raw) - {"observationId", "documentId", "viewId", "detail", "access"}:
            raise ValueError("marketContext must contain only observationId, documentId, viewId, detail and access")
        for key in ("observationId", "documentId", "viewId"):
            if not isinstance(raw.get(key), str) or not raw[key].strip() or len(raw[key]) > 200:
                raise ValueError(f"marketContext.{key} must be a nonempty identifier")
        detail, access = raw.get("detail", "balanced"), raw.get("access", "read")
        if detail not in ("quick", "balanced", "deep") or access not in ("read", "annotate"):
            raise ValueError("marketContext detail or access is invalid")
        return cls(raw["observationId"], raw["documentId"], raw["viewId"], detail, access)

    def to_dict(self) -> dict:
        return {"observationId": self.observation_id, "documentId": self.document_id,
                "viewId": self.view_id, "detail": self.detail, "access": self.access}


@dataclass(frozen=True)
class ChatSendRequest:
    """Normalized chat send request."""

    session_key: str
    message: str
    idempotency_key: str | None = None
    # Chat attachment ids (resolved to inline images for the model). Tuple keeps
    # the frozen dataclass hashable; default empty for text-only sends.
    attachment_ids: tuple[str, ...] = ()
    # Structured operator intent for this turn. These ids are validated against
    # the registry and Access policy before they influence the hidden prompt.
    requested_tool_ids: tuple[str, ...] = ()
    provider: str = "openai-codex"
    model: str | None = None
    system_prompt_id: str | None = None
    task_prompt_id: str | None = None
    persona_id: str | None = None
    persona_flavor_id: str | None = None
    persona_privacy_tier: PersonaPrivacyTier | None = None
    timeout_ms: int | None = None
    system_prompt: str | None = None
    allow_tools: bool = True
    workspace_root: str | None = None
    market_context: MarketContextRequest | None = None
