"""Persisted schedules skip startup and sleep backlog, including DST anomalies."""
import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from copenet.core.market import sentinel
from copenet.core.market.scans.definitions import default_scan, next_run_at


@pytest.mark.parametrize(("current", "expected"), [
    ("2026-09-03T13:00:00+00:00", "2026-09-03T13:45:00+00:00"),
    ("2026-09-03T13:45:00+00:00", "2026-09-04T13:45:00+00:00"),
    ("2026-09-03T18:00:00+00:00", "2026-09-04T13:45:00+00:00"),
])
def test_default_scan_waits_for_strictly_future_0945(monkeypatch, current, expected):
    monkeypatch.delenv("COPNET_MARKET_BRIEF_TIME", raising=False)
    scan = default_scan([])
    scan["timezone"] = "America/New_York"
    assert next_run_at(scan, datetime.fromisoformat(current)) == datetime.fromisoformat(expected)


@pytest.mark.parametrize("value", ["25:00", "09:60", "-1:00", "invalid", ""])
def test_invalid_migration_time_falls_back_to_0945(monkeypatch, value):
    monkeypatch.setenv("COPNET_MARKET_BRIEF_TIME", value)
    assert default_scan([])["times"] == ["09:45"]


def test_days_multiple_times_and_dst():
    scan = {**default_scan([]), "timezone": "America/New_York", "days": [0, 1, 2, 3, 4], "times": ["09:45", "16:15"]}
    assert next_run_at(scan, datetime(2026, 9, 4, 21, tzinfo=timezone.utc)).isoformat() == "2026-09-07T13:45:00+00:00"
    scan.update(days=list(range(7)), times=["02:30"])
    assert next_run_at(scan, datetime(2026, 3, 8, 6, tzinfo=timezone.utc)).isoformat() == "2026-03-09T06:30:00+00:00"


@pytest.mark.asyncio
@pytest.mark.parametrize(("wake_delay", "expected"), [(0, 1), (120, 0)])
async def test_scheduler_skips_sleep_catchup(monkeypatch, wake_delay, expected):
    monkeypatch.setenv('COPNET_MARKET_SENTINEL', '1')
    current = datetime(2026, 9, 3, 13, 44, 59, tzinfo=timezone.utc)
    scan = {**default_scan([]), "timezone": "America/New_York", "times": ["09:45"]}
    waits = []
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return current
    async def sleep(delay):
        nonlocal current
        waits.append(delay)
        if len(waits) == 2:
            raise asyncio.CancelledError
        current += timedelta(seconds=delay + wake_delay)
    service = SimpleNamespace(store=SimpleNamespace(definitions=lambda: [scan]), run=AsyncMock(), tasks=set())
    monkeypatch.setattr(sentinel, "datetime", Clock)
    monkeypatch.setattr(sentinel.asyncio, "sleep", sleep)
    monkeypatch.setattr(sentinel, "resolve_scan_service", lambda _: service)
    monkeypatch.setattr(sentinel, "monitoring_delivery_tick", AsyncMock())
    with pytest.raises(asyncio.CancelledError):
        await sentinel.MarketSentinel(object())._loop()
    await _yield_tasks()
    assert service.run.await_count == expected


async def _yield_tasks():
    task = asyncio.create_task(asyncio.to_thread(lambda: None))
    await task


@pytest.mark.asyncio
async def test_slow_delivery_does_not_block_scan_admission_or_spawn_overlapping_ticks(monkeypatch):
    monkeypatch.setenv('COPNET_MARKET_SENTINEL', '1')
    current = datetime(2026, 9, 3, 13, 44, 59, tzinfo=timezone.utc)
    scan = {**default_scan([]), "timezone": "America/New_York", "times": ["09:45"]}
    service = SimpleNamespace(store=SimpleNamespace(definitions=lambda: [scan]), run=AsyncMock(), tasks=set())
    tick_calls = []
    blocked = asyncio.Event()
    real_sleep = asyncio.sleep
    waits = 0

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return current

    async def slow_delivery(orchestrator):
        tick_calls.append(orchestrator)
        await blocked.wait()

    async def schedule_sleep(delay):
        nonlocal current, waits
        await real_sleep(0)
        waits += 1
        if waits == 3:
            raise asyncio.CancelledError
        current += timedelta(seconds=delay)

    monkeypatch.setattr(sentinel, "datetime", Clock)
    monkeypatch.setattr(sentinel, "resolve_scan_service", lambda _: service)
    monkeypatch.setattr(sentinel, "monitoring_delivery_tick", slow_delivery)
    monkeypatch.setattr(sentinel.asyncio, "sleep", schedule_sleep)
    scheduler = sentinel.MarketSentinel(object())
    with pytest.raises(asyncio.CancelledError):
        await scheduler._loop()
    assert service.run.await_count == 1
    assert len(tick_calls) == 1
    assert not scheduler._delivery_task.done()
    scheduler.stop()
    with pytest.raises(asyncio.CancelledError):
        await scheduler._delivery_task
