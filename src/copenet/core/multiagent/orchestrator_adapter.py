"""Adapter tying provider selection + fallback into one turn entrypoint.

`MultiAgentOrchestrator.run_turn` is the integration surface: given the
model-declared route (and optional capability profile), it selects a provider
chain and runs it with fallback via an injected `run_on_provider` callable. The
callable receives the resolved provider INSTANCE and id and returns whatever the
caller wants (typically the streamed/awaited result of ChatHarness.run_turn for
that provider).

Kept decoupled from the live send_chat runtime so it can be wired in
incrementally and unit-tested in isolation.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from .fallback_executor import FallbackOutcome, ShouldRetry, execute_with_fallback
from .provider_selector import ProviderRoleMap, ProviderSelection, select_provider_chain


TraceRecorder = Callable[[str, dict[str, Any] | None], None]
# Run a turn against one resolved provider. (provider_instance, provider_id) -> result.
RunOnProvider = Callable[[Any, str], Awaitable[Any]]


@dataclass(frozen=True)
class MultiAgentTurnResult:
    """Outcome of one multi-agent turn: the selection plus the fallback outcome."""

    selection: ProviderSelection
    outcome: FallbackOutcome

    @property
    def ok(self) -> bool:
        return self.outcome.ok

    @property
    def provider_id(self) -> str | None:
        return self.outcome.provider_id

    @property
    def value(self) -> Any:
        return self.outcome.value


class MultiAgentOrchestrator:
    """Selects and runs a provider chain for a turn, with fallback."""

    def __init__(
        self,
        *,
        providers: dict[str, Any],
        role_map: ProviderRoleMap | None = None,
        trace: TraceRecorder | None = None,
    ) -> None:
        self._providers = dict(providers)
        self._role_map = role_map or ProviderRoleMap()
        self._trace = trace

    @property
    def available_provider_ids(self) -> list[str]:
        return sorted(self._providers)

    def plan_selection(
        self,
        *,
        route: str | None,
        capability_profile: Any | None = None,
    ) -> ProviderSelection:
        """Resolve the provider chain for a route without running anything."""
        return select_provider_chain(
            route=route,
            available_provider_ids=self.available_provider_ids,
            role_map=self._role_map,
            capability_profile=capability_profile,
            trace=self._trace,
        )

    async def run_turn(
        self,
        *,
        route: str | None,
        run_on_provider: RunOnProvider,
        capability_profile: Any | None = None,
        should_retry: ShouldRetry | None = None,
        abort_event: asyncio.Event | None = None,
        timeout_s: float | None = None,
    ) -> MultiAgentTurnResult:
        """Select a provider chain for the route and run it with fallback."""
        selection = self.plan_selection(route=route, capability_profile=capability_profile)

        async def run_one(provider_id: str) -> Any:
            provider = self._providers[provider_id]
            return await run_on_provider(provider, provider_id)

        outcome = await execute_with_fallback(
            chain=selection.chain,
            run_one=run_one,
            should_retry=should_retry,
            abort_event=abort_event,
            timeout_s=timeout_s,
            trace=self._trace,
        )
        return MultiAgentTurnResult(selection=selection, outcome=outcome)
