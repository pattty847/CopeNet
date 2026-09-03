"""Market delivery RPCs validate operator actions and expose no private destination target."""

from types import SimpleNamespace

import pytest

from copenet.core.messaging.market_delivery import enqueue_market_test
from copenet.core.messaging.market_outbox import MarketOutbox
from copenet.core.messaging.store import MessageDestinationRecord, MessagingConfigRecord
from copenet.host import rpc_market_notifications as rpc


@pytest.fixture
def context(tmp_path, monkeypatch):
    config = MessagingConfigRecord(destinations=[MessageDestinationRecord('synthetic-dest', 'telegram', '@test', 'Test destination')])
    orchestrator = SimpleNamespace(_messaging_store=SimpleNamespace(load=lambda: config))
    monkeypatch.setattr(rpc, '_root', lambda orchestrator: tmp_path)
    monkeypatch.delenv('COPNET_TELEGRAM_BOT_TOKEN', raising=False)
    return tmp_path, orchestrator


@pytest.mark.asyncio
async def test_get_does_not_process_or_send(context, monkeypatch):
    _, orchestrator = context
    frames = []
    async def send(frame):
        frames.append(frame)
    monkeypatch.setattr(rpc, 'process_market_deliveries', lambda *args, **kwargs: pytest.fail('Read started delivery'))
    await rpc.handle_market_notifications_get('read', None, send, orchestrator)
    assert frames[0]['payload']['transportConfigured'] is False
    assert frames[0]['payload']['destinations'] == [dict(id='synthetic-dest', displayName='Test destination', status='configured', requiresApproval=True)]


@pytest.mark.asyncio
async def test_explicit_test_only_processes_created_test_delivery(context, monkeypatch):
    root, orchestrator = context
    calls = []
    async def send(frame):
        pass
    monkeypatch.setattr(rpc, 'process_market_deliveries', lambda *args, **kwargs: calls.append(kwargs))
    await rpc.handle_market_notifications_test('test', {'destinationId': 'synthetic-dest'}, send, orchestrator)
    row = MarketOutbox(root).rows()[0]
    assert row['alertId'] is None
    assert calls == [{'only_delivery_id': row['id']}]
    with pytest.raises(ValueError, match='existing Telegram'):
        await rpc.handle_market_notifications_test('test', {'destinationId': 'not-present'}, send, orchestrator)


@pytest.mark.asyncio
async def test_uncertain_retry_requires_real_boolean_acknowledgment(context, monkeypatch):
    root, orchestrator = context
    row = enqueue_market_test(root, 'synthetic-dest')
    box = MarketOutbox(root)
    stored = box.rows()[0]
    stored['status'] = 'uncertain'
    box.save(stored)
    async def send(frame):
        pass
    monkeypatch.setattr(rpc, 'process_market_deliveries', lambda *args, **kwargs: None)
    params = {'deliveryId': row['id'], 'action': 'retry'}
    with pytest.raises(ValueError, match='duplicate'):
        await rpc.handle_market_notifications_action('retry', params, send, orchestrator)
    with pytest.raises(ValueError, match='boolean'):
        await rpc.handle_market_notifications_action('retry', {**params, 'acknowledgeDuplicateRisk': 'true'}, send, orchestrator)
    await rpc.handle_market_notifications_action('retry', {**params, 'acknowledgeDuplicateRisk': True}, send, orchestrator)
    assert box.rows()[0]['status'] == 'queued'
