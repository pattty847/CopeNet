"""Provider base contracts for CLI-backed model adapters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import AsyncIterator, Literal, Protocol
import asyncio


ProviderEventKind = Literal["delta", "meta", "final"]


@dataclass(frozen=True)
class ProviderEvent:
    """Normalized provider stream event."""

    kind: ProviderEventKind
    text: str | None = None
    provider_session_id: str | None = None


class Provider(Protocol):
    """Provider run contract for orchestrator integration."""

    name: str

    async def run(
        self,
        prompt: str,
        provider_session_id: str | None,
        abort_event: asyncio.Event,
    ) -> AsyncIterator[ProviderEvent]:
        """Run one chat turn and stream normalized events."""
