"""Chain execution with fallback across providers.

Runs an ordered provider chain via an injected `run_one(provider_id)` coroutine:
try the primary; on error, timeout, or an "uncertain" successful result, fall
through to the next provider; record every attempt for tracing. Returns the
first successful outcome (or a failed outcome if the chain is exhausted).

Decoupled from the harness on purpose — `run_one` is whatever the caller wants
to run for a given provider id (a full ChatHarness.run_turn, a one-shot probe,
or a stub in tests).
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable


TraceRecorder = Callable[[str, dict[str, Any] | None], None]
RunOne = Callable[[str], Awaitable[Any]]
# Predicate over a SUCCESSFUL value: return True to reject it and try the next
# provider anyway (the "Claude is uncertain -> ask Gemini" case).
ShouldRetry = Callable[[Any], bool]


@dataclass(frozen=True)
class FallbackAttempt:
    """One provider attempt within a fallback chain."""

    provider_id: str
    ok: bool
    elapsed_ms: int
    error: str | None = None
    # Set when a successful result was rejected by should_retry (soft failure).
    rejected: bool = False


@dataclass(frozen=True)
class FallbackOutcome:
    """Result of running a provider chain with fallback."""

    ok: bool
    provider_id: str | None
    value: Any
    attempts: tuple[FallbackAttempt, ...] = field(default_factory=tuple)

    @property
    def used_fallback(self) -> bool:
        """True if more than one provider was attempted before success/exhaustion."""
        return len(self.attempts) > 1


async def execute_with_fallback(
    *,
    chain: list[str] | tuple[str, ...],
    run_one: RunOne,
    should_retry: ShouldRetry | None = None,
    abort_event: asyncio.Event | None = None,
    timeout_s: float | None = None,
    trace: TraceRecorder | None = None,
) -> FallbackOutcome:
    """Try each provider in `chain` until one succeeds.

    A provider attempt fails (and falls through) when run_one raises, times out
    (timeout_s, via asyncio.wait_for), or returns a value that `should_retry`
    rejects. The first accepted value wins.
    """
    attempts: list[FallbackAttempt] = []
    if not chain:
        if trace is not None:
            trace("multiagent_fallback_empty", {"reason": "empty chain"})
        return FallbackOutcome(ok=False, provider_id=None, value=None, attempts=())

    for index, provider_id in enumerate(chain):
        if abort_event is not None and abort_event.is_set():
            if trace is not None:
                trace("multiagent_aborted", {"providerId": provider_id, "attempt": index + 1})
            break
        started = time.monotonic()
        if trace is not None:
            trace(
                "multiagent_attempt",
                {"providerId": provider_id, "attempt": index + 1, "chainLength": len(chain)},
            )
        try:
            coro = run_one(provider_id)
            value = await (asyncio.wait_for(coro, timeout_s) if timeout_s else coro)
        except Exception as exc:  # noqa: BLE001 — chain fallback is the whole point
            elapsed_ms = int((time.monotonic() - started) * 1000)
            error = f"{exc.__class__.__name__}: {exc}" if str(exc) else exc.__class__.__name__
            attempts.append(
                FallbackAttempt(provider_id=provider_id, ok=False, elapsed_ms=elapsed_ms, error=error)
            )
            if trace is not None:
                trace(
                    "multiagent_fallback",
                    {"providerId": provider_id, "attempt": index + 1, "error": error, "elapsedMs": elapsed_ms},
                )
            continue

        elapsed_ms = int((time.monotonic() - started) * 1000)
        if should_retry is not None and should_retry(value):
            attempts.append(
                FallbackAttempt(
                    provider_id=provider_id, ok=False, elapsed_ms=elapsed_ms, error=None, rejected=True
                )
            )
            if trace is not None:
                trace(
                    "multiagent_fallback",
                    {"providerId": provider_id, "attempt": index + 1, "rejected": True, "elapsedMs": elapsed_ms},
                )
            continue

        attempts.append(FallbackAttempt(provider_id=provider_id, ok=True, elapsed_ms=elapsed_ms))
        if trace is not None:
            trace(
                "multiagent_completed",
                {
                    "providerId": provider_id,
                    "attempt": index + 1,
                    "usedFallback": len(attempts) > 1,
                    "elapsedMs": elapsed_ms,
                },
            )
        return FallbackOutcome(ok=True, provider_id=provider_id, value=value, attempts=tuple(attempts))

    if trace is not None:
        trace(
            "multiagent_exhausted",
            {"chain": list(chain), "attemptCount": len(attempts)},
        )
    return FallbackOutcome(ok=False, provider_id=None, value=None, attempts=tuple(attempts))
