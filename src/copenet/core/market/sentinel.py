"""One persisted scan scheduler. Startup/sleep never replay missed occurrences."""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone

from .scans.definitions import next_run_at
from .scans.service import resolve_scan_service
from .monitoring_delivery import monitoring_delivery_tick

_LOG = logging.getLogger(__name__)
_SCHEDULE_GRACE_SECONDS = 60


def sentinel_enabled() -> bool:
    return os.environ.get("COPNET_MARKET_SENTINEL", "1").strip() != "0"


class MarketSentinel:
    def __init__(self, orchestrator) -> None:
        self._orchestrator = orchestrator
        self._task: asyncio.Task | None = None
        self._delivery_task: asyncio.Task | None = None
        self._scan_tasks: set[asyncio.Task] = set()

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop(), name="market-sentinel")

    def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            self._task = None
        for task in self._scan_tasks:
            task.cancel()
        if self._delivery_task is not None:
            self._delivery_task.cancel()

    def _launch_delivery(self) -> None:
        if self._delivery_task is not None and not self._delivery_task.done():
            return
        self._delivery_task = asyncio.create_task(
            monitoring_delivery_tick(self._orchestrator), name="market-delivery",
        )

        def completed(finished):
            if not finished.cancelled() and finished.exception():
                _LOG.warning("Market notification delivery failed; pending evidence remains durable: %s", finished.exception())

        self._delivery_task.add_done_callback(completed)

    def _launch(self, service, scan, target):
        task = asyncio.create_task(service.run(scan["id"], reason="scheduled", scheduled_at=target.isoformat(), expected_revision=scan["revision"]), name=f"market-scan-{scan['id']}")
        self._scan_tasks.add(task)
        service.tasks.add(task)

        def completed(finished):
            self._scan_tasks.discard(finished)
            service.tasks.discard(finished)
            if not finished.cancelled() and finished.exception():
                _LOG.warning("Scheduled market scan did not run: %s", finished.exception())

        task.add_done_callback(completed)

    async def _loop(self) -> None:
        service = resolve_scan_service(self._orchestrator)
        targets = {}
        while True:
            # A slow Telegram response must not turn an on-time scan into a missed run.
            # One tracked tick also bounds background threads during transport outages.
            self._launch_delivery()
            now = datetime.now(timezone.utc)
            scans = service.store.definitions()
            keys = {(scan["id"], scan["revision"]) for scan in scans}
            targets = {key: value for key, value in targets.items() if key in keys}
            for scan in scans:
                key = (scan["id"], scan["revision"])
                if key not in targets:
                    targets[key] = next_run_at(scan, now)
                target = targets[key]
                if target is None or now < target:
                    continue
                targets[key] = next_run_at(scan, now)
                if not sentinel_enabled() or (now - target).total_seconds() > _SCHEDULE_GRACE_SECONDS:
                    continue
                self._launch(service, scan, target)
            # Scan acquisition runs under its own root lease. It must not block delivery
            # retries or admission of another on-time job while a large scan is running.
            await asyncio.sleep(15)
