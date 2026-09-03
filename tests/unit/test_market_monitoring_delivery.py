"""Real isolated stores prove scan events reach notifications without new acquisition."""

import asyncio
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from copenet.core.market import monitoring_delivery, sentinel
from copenet.core.market.alert_rules import AlertRule
from copenet.core.market.alerts import resolve_alert_store
from copenet.core.market.runtime import MarketRuntime
from copenet.core.market.store import MarketStore
from copenet.core.market.scans.service import resolve_scan_service
from copenet.core.messaging.market_outbox import MarketOutbox
from copenet.core.messaging.store import MessagingConfigRecord, MessageDestinationRecord
from copenet.core.pulse import PulseStore


@pytest.fixture
def context(tmp_path, monkeypatch):
    monkeypatch.delenv('COPNET_TELEGRAM_BOT_TOKEN', raising=False)
    runtime = MarketRuntime(store=MarketStore(tmp_path / 'market'))
    config = MessagingConfigRecord(destinations=[MessageDestinationRecord('test-destination', 'telegram', '@synthetic', 'Test chat')])
    orchestrator = SimpleNamespace(_market_runtime=runtime, _pulse_store=PulseStore(tmp_path / 'pulse.json'),
                                   _messaging_store=SimpleNamespace(load=lambda: config))
    rule = AlertRule('test-alert', 1, 'TEST', 'daily', 'morning', False, True, 'above',
                     {'kind': 'price'}, {'kind': 'constant', 'value': 105}, ['test-destination'], True,
                     'triggered', '2026-01-05T22:00:00Z', '2026-01-06T22:00:00Z')
    store = resolve_alert_store(runtime)
    with store.transaction():
        store._save([rule])
    event = dict(eventId='test-event', alertId=rule.alertId, revision=1, symbol='TEST', timeframe='daily',
                 condition='Close crosses above 105', leftValue=110, rightValue=105,
                 candleCloseAt='2026-01-06T21:00:00Z', evaluatedAt='2026-01-06T22:00:00Z',
                 scanId='morning', destinationIds=rule.destinationIds, rule=rule.to_wire())
    return orchestrator, event


@pytest.mark.asyncio
async def test_scan_factory_callback_publishes_once_and_preserves_dismissed_pulse(context):
    orchestrator, event = context
    service = resolve_scan_service(orchestrator)
    await service.post_prices([event])
    root = service.runtime.store.root_dir
    assert len(MarketOutbox(root).rows()) == 1
    pulse = orchestrator._pulse_store.get(event['eventId'])
    assert pulse.summary == event['condition']
    orchestrator._pulse_store.save(replace(pulse, status='dismissed'))
    await service.post_prices([event])
    assert len(MarketOutbox(root).rows()) == 1
    assert orchestrator._pulse_store.get(event['eventId']).status == 'dismissed'


@pytest.mark.asyncio
async def test_tick_recovers_persisted_event_and_retries_delivery_without_scanning(context, monkeypatch):
    orchestrator, event = context
    runtime = orchestrator._market_runtime
    store = resolve_alert_store(runtime)
    with store.transaction():
        store._append_event(event)
    monkeypatch.setattr(runtime, 'refresh', AsyncMock(side_effect=AssertionError('Delivery must not scan')))
    await monitoring_delivery.monitoring_delivery_tick(orchestrator)
    rows = MarketOutbox(runtime.store.root_dir).rows()
    assert rows[0]['status'] == 'failed'  # No bot credential in this isolated test.
    assert len(rows[0]['attempts']) == 1
    assert orchestrator._pulse_store.get(event['eventId']) is not None
    await monitoring_delivery.monitoring_delivery_tick(orchestrator)
    assert len(MarketOutbox(runtime.store.root_dir).rows()[0]['attempts']) == 1
    runtime.refresh.assert_not_called()


@pytest.mark.asyncio
async def test_scheduler_processes_deliveries_with_no_scheduled_scans(context, monkeypatch):
    orchestrator, _ = context
    monkeypatch.setenv('COPNET_MARKET_SENTINEL', '0')
    service = SimpleNamespace(store=SimpleNamespace(definitions=lambda: []), run=AsyncMock())
    tick = AsyncMock()
    monkeypatch.setattr(sentinel, 'resolve_scan_service', lambda _: service)
    monkeypatch.setattr(sentinel, 'monitoring_delivery_tick', tick)
    async def stop(delay):
        raise asyncio.CancelledError
    monkeypatch.setattr(sentinel.asyncio, 'sleep', stop)
    scheduler = sentinel.MarketSentinel(orchestrator)
    with pytest.raises(asyncio.CancelledError):
        await scheduler._loop()
    await scheduler._delivery_task
    tick.assert_awaited_once_with(orchestrator)
    service.run.assert_not_called()


@pytest.mark.asyncio
async def test_cancel_rule_rpc_cancels_pending_delivery(context):
    from copenet.host.rpc_market_alerts import handle_market_alerts_cancel
    orchestrator, event = context
    await monitoring_delivery.on_scan_alert_events(orchestrator, [event])
    frames = []
    async def send(frame):
        frames.append(frame)
    await handle_market_alerts_cancel('cancel', {'alertId': event['alertId']}, send, orchestrator)
    rows = MarketOutbox(orchestrator._market_runtime.store.root_dir).rows()
    assert rows[0]['status'] == 'cancelled'
    assert not rows[0]['attempts']
    assert frames[0]['ok'] is True
