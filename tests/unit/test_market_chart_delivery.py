"""Synthetic chart notification evidence and mocked Telegram photo transport."""
from io import BytesIO
from urllib.error import URLError
import json

from PIL import Image
import pytest

from copenet.core.market.alert_chart import render_alert_chart
from copenet.core.messaging.market_delivery import enqueue_market_event, process_market_deliveries, market_event_message
from copenet.core.messaging.market_outbox import MarketOutbox
from copenet.core.messaging.store import MessageDestinationRecord, MessagingConfigRecord
from copenet.core.messaging.telegram_delivery import send_telegram_photo, TelegramReceipt


@pytest.fixture
def event():
    return dict(eventId='chart-event', alertId='alert', revision=1, symbol='TEST', timeframe='weekly',
        condition='Low reaches Supertrend', leftValue=95, rightValue=96, phase='interaction',
        candleCloseAt='2026-09-11T20:00:00Z', evaluatedAt='2026-09-09T15:00:00Z',
        rule={'includeChart': True, 'includePosition': True, 'left': {'kind': 'price', 'field': 'low'},
              'right': {'kind': 'constant', 'value': 96}},
        position={'quantity': 10, 'avg_cost': 90, 'unrealized_pl': 50, 'unrealized_pl_pct': 5.56,
                  'allocation_pct': None, 'currency': 'USD', 'synced_at': '2026-09-08T20:00:00Z'},
        chartSnapshot={'bars': [{'t': 1788739200 + i*86400, 'o': 100, 'h': 102, 'l': 95, 'c': 98, 'v': 200} for i in range(3)],
                       'points': [{'t': 1788739200 + i*86400, 'left': 95, 'right': 96} for i in range(3)],
                       'priceBasis': 'split_adjusted', 'reference': 'previous_completed'})


def config():
    return MessagingConfigRecord(destinations=[MessageDestinationRecord('test', 'telegram', '@synthetic', 'Test')])


def test_chart_is_deterministic_png_without_account_content(event):
    image = render_alert_chart(event)
    event['position']['quantity'] = 999
    assert render_alert_chart(event) == image
    assert Image.open(BytesIO(image)).size == (1200, 820)


def test_position_is_opt_in_and_missing_values_are_unknown(event):
    text = market_event_message(event)
    assert 'Weight unknown' in text
    assert 'Broker snapshot: 2026-09-08' in text
    assert 'Candle closes:' in text
    event['rule']['includePosition'] = False
    assert 'Position:' not in market_event_message(event)


def test_single_photo_keeps_original_evidence_and_uncertain_receipt(tmp_path, event):
    enqueue_market_event(tmp_path, event, ['test'], authorized=True)
    original = MarketOutbox(tmp_path).rows()[0]
    event['leftValue'] = 999
    enqueue_market_event(tmp_path, event, ['test'], authorized=True)
    calls = []
    def photo(*args):
        calls.append(args)
        return TelegramReceipt('uncertain', error='timeout')
    for _ in range(2):
        rows = process_market_deliveries(tmp_path, config, lambda *args: True,
            transport=lambda *args: pytest.fail('Unexpected text send'), photo_transport=photo)
    assert len(calls) == 1
    assert rows[0]['status'] == 'uncertain'
    assert 'photo' not in rows[0] and 'evidence' not in rows[0]
    assert original['evidence']['leftValue'] == 95
    assert len(calls[0][1].encode('utf-16-le')) // 2 <= 1024
    assert calls[0][2].startswith(b'\x89PNG')


def test_long_caption_is_bounded_but_evidence_is_not(tmp_path, event):
    event['condition'] = '😀' * 3000
    enqueue_market_event(tmp_path, event, ['test'], authorized=True)
    row = MarketOutbox(tmp_path).rows()[0]
    assert len(row['caption'].encode('utf-16-le')) // 2 <= 1024
    assert row['evidence']['condition'] == event['condition']
    assert 'Full evidence saved' in row['caption']


def test_chart_failure_falls_back_before_send_and_respects_approval(tmp_path, event):
    event['chartSnapshot']['bars'] = []
    enqueue_market_event(tmp_path, event, ['test'])
    rows = process_market_deliveries(tmp_path, config, lambda *args: True,
        transport=lambda *args: pytest.fail('No consent'), photo_transport=lambda *args: pytest.fail('No consent'))
    assert rows[0]['status'] == 'approval_required'
    assert not rows[0]['hasChart']
    assert 'Chart snapshot unavailable' in rows[0]['text']


def test_photo_transport_uploads_one_multipart_receipt(monkeypatch, event):
    monkeypatch.setenv('COPNET_TELEGRAM_BOT_TOKEN', '123:synthetic')
    requests = []
    class Response(BytesIO):
        def __enter__(self):
            return self
    def send(request, **kwargs):
        requests.append(request)
        return Response(json.dumps({'ok': True, 'result': {'message_id': 71}}).encode())
    monkeypatch.setattr('copenet.core.messaging.telegram_delivery.urlopen', send)
    photo = render_alert_chart(event)
    receipt = send_telegram_photo('@synthetic', 'Frozen evidence', photo)
    assert receipt.message_id == 71
    assert len(requests) == 1
    assert requests[0].full_url.endswith('/sendPhoto')
    assert b'name="caption"' in requests[0].data
    assert photo in requests[0].data
    assert send_telegram_photo('@synthetic', '😀' * 513, photo).status == 'failed'
    assert len(requests) == 1


def test_photo_transport_timeout_never_exposes_token(monkeypatch, event):
    monkeypatch.setenv('COPNET_TELEGRAM_BOT_TOKEN', '123:synthetic')
    def fail(*args, **kwargs):
        raise URLError('https://api.telegram.org/bot123:synthetic/sendPhoto')
    monkeypatch.setattr('copenet.core.messaging.telegram_delivery.urlopen', fail)
    receipt = send_telegram_photo('@synthetic', 'test', render_alert_chart(event))
    assert receipt.status == 'uncertain'
    assert 'synthetic' not in receipt.error


def test_snapshot_labels_and_observation_time_describe_frozen_confirmation(event):
    event['observedAt'] = '2026-09-09T14:45:00Z'
    event['chartSnapshot'].update(leftLabel='Close', rightLabel='MAMA output')
    original = render_alert_chart(event)
    event['rule']['left']['field'] = 'high'
    event['rule']['right']['value'] = 777
    event['evaluatedAt'] = '2026-09-09T15:30:00Z'
    assert render_alert_chart(event) == original
    assert 'Data observed: 2026-09-09T14:45:00Z' in market_event_message(event)
