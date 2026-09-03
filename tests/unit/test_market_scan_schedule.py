"""Scheduled scans are explicit slots, never startup catch-up work."""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from copenet.core.market import sentinel


@pytest.mark.parametrize(("current", "expected"), [
    ("2026-09-03T09:00:00", "2026-09-03T09:45:00"),
    ("2026-09-03T09:44:59", "2026-09-03T09:45:00"),
    ("2026-09-03T09:45:00", "2026-09-04T09:45:00"),
    ("2026-09-03T12:00:00", "2026-09-04T09:45:00"),
    ("2026-09-30T23:59:59", "2026-10-01T09:45:00"),
])
def test_default_scan_waits_for_next_future_0945_slot(monkeypatch, current, expected):
    monkeypatch.delenv("COPNET_MARKET_BRIEF_TIME", raising=False)
    assert sentinel._next_sweep_at(datetime.fromisoformat(current)) == datetime.fromisoformat(expected)


@pytest.mark.parametrize("value", ["25:00", "09:60", "-1:00", "invalid", ""])
def test_invalid_schedule_falls_back_to_0945_without_wrapping(monkeypatch, value):
    monkeypatch.setenv("COPNET_MARKET_BRIEF_TIME", value)
    assert sentinel._brief_time() == (9, 45)


def test_explicit_time_override_is_preserved(monkeypatch):
    monkeypatch.setenv("COPNET_MARKET_BRIEF_TIME", "16:30")
    assert sentinel._next_sweep_at(datetime(2026, 9, 3, 12)) == datetime(2026, 9, 3, 16, 30)


@pytest.mark.asyncio
@pytest.mark.parametrize(("wake_delay", "fails", "expected_runs"), [(0, False, 1), (120, False, 0), (0, True, 1)])
async def test_loop_skips_sleep_catchup_and_does_not_retry_failed_scan(monkeypatch, wake_delay, fails, expected_runs):
    current = datetime(2026, 9, 3, 9, 44)
    waits = []

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return current.astimezone(tz) if tz else current

    async def sleep(delay):
        nonlocal current
        waits.append(delay)
        if len(waits) == 2:
            raise asyncio.CancelledError
        current += timedelta(seconds=delay + wake_delay)

    run = AsyncMock(side_effect=RuntimeError("synthetic failure") if fails else None)
    monkeypatch.delenv("COPNET_MARKET_BRIEF_TIME", raising=False)
    monkeypatch.setattr(sentinel, "datetime", Clock)
    monkeypatch.setattr(sentinel.asyncio, "sleep", sleep)
    monkeypatch.setattr(sentinel, "resolve_market_runtime", lambda _: object())
    monkeypatch.setattr(sentinel, "run_morning_sweep", run)
    with pytest.raises(asyncio.CancelledError):
        await sentinel.MarketSentinel(object())._loop()
    assert run.await_count == expected_runs
    assert waits[0] == 60
    assert waits[1] > 23 * 3600  # no ten-minute retry or catch-up path
