"""Provider base contracts for model adapters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, AsyncIterator, Literal, Protocol
import asyncio


ProviderEventKind = Literal["delta", "reasoning_delta", "meta", "final"]


@dataclass(frozen=True)
class ProviderEvent:
    """Normalized provider stream event."""

    kind: ProviderEventKind
    text: str | None = None
    provider_session_id: str | None = None
    metadata: dict[str, Any] | None = None


# Meta key carrying the model that actually answered, as distinct from the model
# that was requested. These diverge for real: LM Studio resolves a request against
# whatever instance is currently loaded, and a run stamped with the requested id
# cannot tell you what produced the output. Before this existed, 95 of 334 local
# traces (28%) carried a null model at all.
RESOLVED_MODEL_META_KEY = "resolvedModel"


# Meta key carrying one model call's token usage as the provider reported it.
# Every provider that can see usage emits one of these per model response; the
# orchestrator sums them into the run record. Estimates never travel under this
# key — a reader must be able to trust that the number came from the provider.
TOKEN_USAGE_META_KEY = "tokenUsage"


def token_usage_event(
    *,
    input_tokens: int | None,
    output_tokens: int | None,
    cached_input_tokens: int | None = None,
    reasoning_tokens: int | None = None,
) -> ProviderEvent | None:
    """Return the meta event for one reported usage block, or None when nothing was reported."""
    def _count(value) -> int | None:
        return int(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0 else None
    usage = {
        "inputTokens": _count(input_tokens),
        "outputTokens": _count(output_tokens),
        "cachedInputTokens": _count(cached_input_tokens),
        "reasoningTokens": _count(reasoning_tokens),
    }
    if usage["inputTokens"] is None and usage["outputTokens"] is None:
        return None
    return ProviderEvent(kind="meta", metadata={TOKEN_USAGE_META_KEY: usage})


def resolved_model_event(model: str | None) -> ProviderEvent | None:
    """Return the meta event announcing the model that actually ran, or None."""
    normalized = str(model or "").strip()
    if not normalized:
        return None
    return ProviderEvent(kind="meta", metadata={RESOLVED_MODEL_META_KEY: normalized})


@dataclass(frozen=True)
class ProviderModel:
    """One selectable model exposed by a provider."""

    id: str
    display_name: str
    provider: str
    description: str | None = None
    kind: str = "chat"
    capabilities: dict[str, bool] | None = None
    recommended_for: list[str] | None = None
    metadata: dict[str, Any] | None = None


class Provider(Protocol):
    """Provider run contract for orchestrator integration.

    Implementations must set ``name`` (stable id) and ``display_name`` (short UI label).
    """

    name: str
    display_name: str

    async def run(
        self,
        prompt: str,
        provider_session_id: str | None,
        abort_event: asyncio.Event,
        model: str | None = None,
        system_prompt: str | None = None,
    ) -> AsyncIterator[ProviderEvent]:
        """Run one chat turn and stream normalized events."""

    async def describe(self) -> dict[str, Any]:
        """Return provider availability and UI metadata."""

    async def list_models(self) -> list[ProviderModel]:
        """Return selectable models for this provider."""
