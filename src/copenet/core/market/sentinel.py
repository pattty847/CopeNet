"""Overnight market sentinel — the pre-market sweep that powers the morning brief.

One sweep per day, default 07:00 operator-local (pre-market ET): refresh the
dashboard, diff it against the pre-sweep snapshot into a morning brief, publish
a Pulse inbox item, then chain the automatic whole-market model read (which
now sees the overnight delta in its fact packet).

Env knobs:
  COPNET_MARKET_SENTINEL=0        disable the background loop entirely
  COPNET_MARKET_BRIEF_TIME=HH:MM  sweep time, operator-local (default 07:00)
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta
from typing import Any

from copenet.core.pulse import PulseRecord

from .brief import build_morning_brief, compute_movers
from .runtime import MarketRuntime, resolve_market_runtime

_LOG = logging.getLogger(__name__)

DEFAULT_BRIEF_TIME = "07:00"

# Startup catch-up delay: long enough that short-lived test apps (TestClient
# lifespans) never trigger a real network sweep, short enough that a server
# restarted after brief time still self-heals within a minute.
_CATCHUP_DELAY_SECONDS = 60.0
_RETRY_BACKOFF_SECONDS = 600.0

# Serializes the scheduler-triggered sweep against operator-triggered market.brief.run.
_sweep_lock = asyncio.Lock()


def sentinel_enabled() -> bool:
    return os.environ.get("COPNET_MARKET_SENTINEL", "1").strip() != "0"


def _brief_time() -> tuple[int, int]:
    raw = os.environ.get("COPNET_MARKET_BRIEF_TIME", DEFAULT_BRIEF_TIME).strip()
    try:
        hour, minute = raw.split(":")
        return int(hour) % 24, int(minute) % 60
    except ValueError:
        _LOG.warning("COPNET_MARKET_BRIEF_TIME=%r is not HH:MM — using %s", raw, DEFAULT_BRIEF_TIME)
        return 7, 0


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _sweep_satisfied(existing: dict[str, Any] | None, now: datetime) -> bool:
    """Whether today's scheduled sweep is already covered by the stored brief.

    Before brief time, any same-day brief counts (a pre-dawn manual sweep is current
    enough). At/after brief time, only a brief generated at/after today's brief time
    counts — so a 3 AM manual brief never suppresses the real 7 AM sweep."""
    if not existing or existing.get("briefDate") != now.strftime("%Y-%m-%d"):
        return False
    hour, minute = _brief_time()
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if now < target:
        return True
    raw = str(existing.get("generatedAt") or "")
    try:
        generated = datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone()
    except ValueError:
        return True  # unparseable stamp — treat as satisfied rather than sweep-looping
    return generated >= target.astimezone()


async def run_morning_sweep(
    runtime: MarketRuntime,
    provider,
    pulse_store=None,
    *,
    force: bool = False,
) -> dict[str, Any] | None:
    """Refresh → diff → persist brief → Pulse item → chained model read.

    Idempotent per day unless ``force`` (the operator's "run now" button): a second
    call on the same date returns the existing brief without re-sweeping.
    """
    async with _sweep_lock:
        brief_date = _today()
        existing = runtime.store.load_morning_brief()
        if not force and _sweep_satisfied(existing, datetime.now()):
            return existing

        previous = runtime.store.load_dashboard_wire()
        await asyncio.to_thread(runtime.refresh, scope="all")
        current = runtime.store.load_dashboard_wire()
        brief = build_morning_brief(
            previous,
            current,
            movers=compute_movers(runtime.store),
            brief_date=brief_date,
        )
        wire = brief.to_wire()
        runtime.store.save_morning_brief(wire)
        _LOG.info("morning sweep: brief for %s — %s", brief_date, brief.headline)

        if pulse_store is not None:
            try:
                _publish_pulse(pulse_store, wire)
            except Exception:
                _LOG.warning("morning sweep: pulse publish failed", exc_info=True)

        if provider is not None:
            try:
                await runtime.interpret(provider, target="market")
            except Exception:
                # The deterministic brief still stands; the model read stays stale.
                _LOG.warning("morning sweep: chained model read failed", exc_info=True)
        return wire


def _publish_pulse(pulse_store, wire: dict[str, Any]) -> None:
    brief_date = str(wire.get("briefDate") or _today())
    pulse_id = f"market-brief-{brief_date}"
    existing = pulse_store.get(pulse_id)
    if existing is not None and existing.status != "new":
        return  # the operator already acted on today's item — don't resurrect it
    new_evidence = wire.get("newEvidence") or []
    flips = wire.get("signalFlips") or []
    now = datetime.now().astimezone().isoformat()
    record = PulseRecord(
        pulse_id=pulse_id,
        status="new",
        title=f"Morning market brief · {brief_date}",
        summary=str(wire.get("headline") or "Morning market brief is ready."),
        why_now=(
            f"Pre-market sweep found {len(new_evidence)} new SEC filing(s) and "
            f"{len(flips)} signal flip(s) since the previous sweep."
        ),
        source_session_keys=["market-sentinel"],
        source_run_ids=[],
        created_at=existing.created_at if existing else now,
        updated_at=now,
    )
    if existing is None:
        pulse_store.create(record)
    else:
        pulse_store.save(record)  # a fresher same-day sweep updates the unread item in place


class MarketSentinel:
    """Background loop that fires the morning sweep at brief time every day."""

    def __init__(self, orchestrator) -> None:
        self._orchestrator = orchestrator
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop(), name="market-sentinel")

    def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            self._task = None

    async def _loop(self) -> None:
        runtime = resolve_market_runtime(self._orchestrator)
        while True:
            delay = self._seconds_until_next_sweep(runtime)
            _LOG.info("market sentinel: next sweep in %.0f min", delay / 60)
            await asyncio.sleep(delay)
            try:
                await run_morning_sweep(runtime, self._provider(), self._pulse_store())
            except asyncio.CancelledError:
                raise
            except Exception:
                _LOG.exception("market sentinel: sweep failed — retrying after backoff")
                await asyncio.sleep(_RETRY_BACKOFF_SECONDS)

    def _seconds_until_next_sweep(self, runtime: MarketRuntime) -> float:
        hour, minute = _brief_time()
        now = datetime.now()
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if now >= target:
            if not _sweep_satisfied(runtime.store.load_morning_brief(), now):
                return _CATCHUP_DELAY_SECONDS  # server was down at brief time — catch up
            target += timedelta(days=1)
        return max((target - now).total_seconds(), _CATCHUP_DELAY_SECONDS)

    def _provider(self):
        providers = getattr(self._orchestrator, "_providers", None)
        return providers.get("openai-codex") if isinstance(providers, dict) else None

    def _pulse_store(self):
        return getattr(self._orchestrator, "_pulse_store", None)
