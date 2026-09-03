"""Bridge durable alert evidence to Pulse and Telegram without acquiring market data."""

from __future__ import annotations

import asyncio
from functools import partial

from copenet.core.messaging.market_delivery import enqueue_market_event, process_market_deliveries
from copenet.core.messaging.market_outbox import MarketOutbox
from copenet.core.pulse import PulseRecord
from .alerts import delivery_rule_active, resolve_alert_store
from .runtime import resolve_market_runtime
from .scans.store import file_lock


def publish_monitoring_events(orchestrator, events: list[dict]) -> None:
    """Publish each immutable event once, including recovery after a host interruption."""
    root = resolve_market_runtime(orchestrator).store.root_dir
    box = MarketOutbox(root)
    with file_lock(box.directory / "publication.lock"):
        with box.connection() as connection:
            connection.execute("CREATE TABLE IF NOT EXISTS published_events (event_id TEXT PRIMARY KEY)")
        for event in events:
            with box.connection() as connection:
                if connection.execute("SELECT 1 FROM published_events WHERE event_id=?", (event["eventId"],)).fetchone():
                    continue
            enqueue_market_event(root, event, event["destinationIds"], authorized=event["rule"]["telegramAuthorized"])
            pulse_store = getattr(orchestrator, "_pulse_store", None)
            if pulse_store is not None and pulse_store.get(event["eventId"]) is None:
                pulse_store.create(PulseRecord(
                    pulse_id=event["eventId"], status="new",
                    title=f"{event['symbol']} · {event['timeframe']} technical alert",
                    summary=event["condition"],
                    why_now=f"Completed candle {event['candleCloseAt']}; observed {event['leftValue']} versus {event['rightValue']}.",
                    source_session_keys=["market-alerts"], source_run_ids=[],
                    created_at=event["evaluatedAt"], updated_at=event["evaluatedAt"],
                ))
            # Receipt follows both side effects. Replaying cannot resurrect a dismissed Pulse
            # or duplicate an outbox item if the host stopped between these writes.
            with box.connection() as connection:
                connection.execute("INSERT OR IGNORE INTO published_events VALUES (?)", (event["eventId"],))


async def on_scan_alert_events(orchestrator, events: list[dict]) -> None:
    await asyncio.to_thread(publish_monitoring_events, orchestrator, events)


def _recover_monitoring_events(orchestrator) -> None:
    runtime = resolve_market_runtime(orchestrator)
    store = resolve_alert_store(runtime)
    with store.transaction():
        # The journal is append-only. Pre-migration price events have no eventId and
        # are historical evidence, not authorization for new external notifications.
        events = [event for event in store._events() if "eventId" in event]
    publish_monitoring_events(orchestrator, events)


async def monitoring_delivery_tick(orchestrator) -> None:
    """Called by the existing scheduler even when no scan is due or scans are paused."""
    await asyncio.to_thread(_recover_monitoring_events, orchestrator)
    messaging = getattr(orchestrator, "_messaging_store", None)
    if messaging is not None:
        root = resolve_market_runtime(orchestrator).store.root_dir
        await asyncio.to_thread(process_market_deliveries, root, messaging.load, partial(delivery_rule_active, root))
