"""Synthetic outbox/transport verification; never contacts Telegram or operator stores."""

from dataclasses import replace
from datetime import datetime
import json
from io import BytesIO
import threading
from urllib.error import HTTPError, URLError

import pytest

from copenet.core.messaging.market_delivery import (
    cancel_market_rule_deliveries, enqueue_market_event, enqueue_market_test,
    market_delivery_action, market_event_message, market_notifications_state,
    process_market_deliveries,
)
from copenet.core.messaging.market_outbox import MarketOutbox
from copenet.core.messaging.store import MessageDestinationRecord, MessagingApprovalPolicyRecord, MessagingConfigRecord
from copenet.core.messaging.telegram_delivery import TelegramReceipt, send_telegram_message


@pytest.fixture
def event():
    return dict(eventId="event-1", alertId="alert-1", revision=1, symbol="TEST", timeframe="daily",
                condition="RSI(14) crosses above 30", leftValue=31, rightValue=30,
                candleCloseAt="2026-09-02T20:00:00Z", evaluatedAt="2026-09-03T13:45:00Z")


@pytest.fixture
def config():
    return MessagingConfigRecord(destinations=[MessageDestinationRecord("test-destination", "telegram", "@synthetic", "Test chat")])


def send(root, config, transport=lambda target, text: TelegramReceipt("sent", message_id=42), **kwargs):
    return process_market_deliveries(root, lambda: config, lambda alert_id, revision: True, transport=transport, **kwargs)


def test_event_deduplication_survives_restart_and_keeps_first_evidence(tmp_path, event, config):
    original = enqueue_market_event(tmp_path, event, ["test-destination"], True)[0]
    event["leftValue"] = 999
    assert enqueue_market_event(tmp_path, event, ["test-destination", "test-destination"], True)[0] == original
    calls = []
    assert send(tmp_path, config, lambda *args: calls.append(args) or TelegramReceipt("sent", message_id=42))[0]["status"] == "sent"
    send(tmp_path, config, lambda *args: calls.append(args))
    assert len(calls) == 1
    assert "999" not in calls[0][1]


def test_rule_authorization_is_explicit_even_with_permissive_defaults(tmp_path, event, config):
    config = replace(config, approval_policy=MessagingApprovalPolicyRecord(False),
                     destinations=[replace(config.destinations[0], requires_approval=False)])
    row = enqueue_market_event(tmp_path, event, ["test-destination"])[0]
    assert send(tmp_path, config)[0]["status"] == "approval_required"
    market_delivery_action(tmp_path, row["id"], "approve")
    assert send(tmp_path, config)[0]["status"] == "sent"


@pytest.mark.parametrize("block", ["test-destination", "@synthetic", "telegram:@synthetic"])
def test_rule_grant_never_overrides_hardline_blocklist(tmp_path, event, config, block):
    enqueue_market_event(tmp_path, event, ["test-destination"], True)
    config = replace(config, approval_policy=MessagingApprovalPolicyRecord(True, [block]))
    assert send(tmp_path, config)[0]["status"] == "cancelled"


def test_paused_or_revised_rule_and_disabled_destination_cancel_before_send(tmp_path, event, config):
    enqueue_market_event(tmp_path, event, ["test-destination"], True)
    rows = process_market_deliveries(tmp_path, lambda: config, lambda *args: False)
    assert rows[0]["status"] == "cancelled"
    event["eventId"] = "event-2"
    enqueue_market_event(tmp_path, event, ["test-destination"], True)
    config = replace(config, destinations=[replace(config.destinations[0], status="unconfigured")])
    assert send(tmp_path, config)[0]["status"] == "cancelled"


def test_uncertain_network_result_never_automatically_retries(tmp_path, event, config):
    row = enqueue_market_event(tmp_path, event, ["test-destination"], True)[0]
    assert send(tmp_path, config, lambda *args: TelegramReceipt("uncertain", error="timeout"))[0]["status"] == "uncertain"
    assert send(tmp_path, config)[0]["status"] == "uncertain"
    with pytest.raises(ValueError, match="duplicate"):
        market_delivery_action(tmp_path, row["id"], "retry")
    market_delivery_action(tmp_path, row["id"], "retry", acknowledge_duplicate_risk=True)
    result = send(tmp_path, config)[0]
    assert result["status"] == "sent"
    assert len(result["attempts"]) == 2


def test_sender_crash_recovers_to_uncertain_not_queued(tmp_path, event, config):
    enqueue_market_event(tmp_path, event, ["test-destination"], True)
    box = MarketOutbox(tmp_path)
    row = box.rows()[0]
    row["status"] = "sending"
    box.save(row)
    assert send(tmp_path, config)[0]["status"] == "uncertain"


def test_rate_limit_defers_entire_bot_and_eventually_retries(tmp_path, event, config):
    enqueue_market_event(tmp_path, event, ["test-destination"], True)
    event["eventId"] = "event-2"
    enqueue_market_event(tmp_path, event, ["test-destination"], True)
    calls = []
    rows = send(tmp_path, config, lambda *args: calls.append(args) or TelegramReceipt("queued", retry_after=60), now=1000)
    assert len(calls) == 1
    assert datetime.fromisoformat(rows[-1]["nextAttemptAt"]).timestamp() == 1060
    assert all(row["status"] == "queued" for row in send(tmp_path, config, now=1059))
    assert all(row["status"] == "sent" for row in send(tmp_path, config, now=1060))


def test_outbox_sender_lock_prevents_concurrent_network_writes(tmp_path, event, config):
    enqueue_market_event(tmp_path, event, ["test-destination"], True)
    entered, release = threading.Event(), threading.Event()
    def transport(*args):
        entered.set()
        assert release.wait(5)
        return TelegramReceipt("sent", message_id=1)
    thread = threading.Thread(target=lambda: send(tmp_path, config, transport))
    thread.start()
    assert entered.wait(5)
    assert send(tmp_path, config) == []
    release.set()
    thread.join(5)
    assert MarketOutbox(tmp_path).rows()[0]["status"] == "sent"


def test_test_message_is_fixed_and_does_not_authorize_rule(tmp_path, event, config):
    test_row = enqueue_market_test(tmp_path, "test-destination")
    enqueue_market_event(tmp_path, event, ["test-destination"])
    rows = send(tmp_path, config, only_delivery_id=test_row["id"])
    assert [row["status"] for row in rows] == ["approval_required", "sent"]
    cancel_market_rule_deliveries(tmp_path, "alert-1")
    assert MarketOutbox(tmp_path).rows()[0]["status"] == "cancelled"


def test_public_state_has_no_targets_or_credentials(tmp_path, config, monkeypatch):
    monkeypatch.delenv("COPNET_TELEGRAM_BOT_TOKEN", raising=False)
    state = market_notifications_state(tmp_path, lambda: config)
    assert not state["transportConfigured"]
    assert "@synthetic" not in json.dumps(state)
    assert state["destinations"][0]["displayName"] == "Test chat"


def test_deep_link_never_includes_auth_or_untrusted_host(monkeypatch, event):
    monkeypatch.setenv("COPNET_PUBLIC_URL", "https://example.test?token=secret")
    assert "secret" not in market_event_message(event)
    monkeypatch.setenv("COPNET_PUBLIC_URL", "https://example.test")
    assert "https://example.test/market/TEST" in market_event_message(event)


class Response:
    def __init__(self, body):
        self.body = json.dumps(body).encode()
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass
    def read(self, size):
        return self.body[:size]


@pytest.mark.parametrize("payload,status", [
    ({"ok": True, "result": {"message_id": 12}}, "sent"),
    ({"ok": False, "error_code": 429, "parameters": {"retry_after": 10}}, "queued"),
    ({"ok": False, "error_code": 403, "description": "private target"}, "failed"),
    ({"ok": True, "result": {}}, "uncertain"),
    ({"ok": "true", "result": {"message_id": 12}}, "uncertain"),
])
def test_telegram_adapter_validates_receipts_without_exposing_api_descriptions(monkeypatch, payload, status):
    monkeypatch.setenv("COPNET_TELEGRAM_BOT_TOKEN", "123:synthetic")
    monkeypatch.setattr("copenet.core.messaging.telegram_delivery.urlopen", lambda *args, **kwargs: Response(payload))
    receipt = send_telegram_message("@synthetic", "test")
    assert receipt.status == status
    assert "private target" not in (receipt.error or "")


def test_telegram_adapter_never_leaks_url_from_network_exception(monkeypatch):
    monkeypatch.setenv("COPNET_TELEGRAM_BOT_TOKEN", "123:synthetic")
    def fail(*args, **kwargs):
        raise URLError("https://api.telegram.org/bot123:synthetic/sendMessage")
    monkeypatch.setattr("copenet.core.messaging.telegram_delivery.urlopen", fail)
    receipt = send_telegram_message("@synthetic", "test")
    assert receipt.status == "uncertain"
    assert "123:synthetic" not in receipt.error


def test_telegram_http_429_uses_server_retry_after(monkeypatch):
    monkeypatch.setenv("COPNET_TELEGRAM_BOT_TOKEN", "123:synthetic")
    def rate_limit(*args, **kwargs):
        body = BytesIO(json.dumps({"ok": False, "error_code": 429, "parameters": {"retry_after": 45}}).encode())
        raise HTTPError("https://example.test", 429, "rate limit", {}, body)
    monkeypatch.setattr("copenet.core.messaging.telegram_delivery.urlopen", rate_limit)
    receipt = send_telegram_message("@synthetic", "test")
    assert receipt.status == "queued"
    assert receipt.retry_after == 45


def test_changed_destination_after_failed_attempt_cannot_redirect_retry(tmp_path, event, config):
    row = enqueue_market_event(tmp_path, event, ["test-destination"], True)[0]
    send(tmp_path, config, lambda *args: TelegramReceipt("failed", error="rejected"))
    market_delivery_action(tmp_path, row["id"], "retry")
    config = replace(config, destinations=[replace(config.destinations[0], target="@different")])
    assert send(tmp_path, config)[0]["status"] == "cancelled"


def test_transport_missing_and_long_unicode_messages_do_not_make_requests(monkeypatch):
    monkeypatch.delenv("COPNET_TELEGRAM_BOT_TOKEN", raising=False)
    assert send_telegram_message("@synthetic", "test").status == "failed"
    monkeypatch.setenv("COPNET_TELEGRAM_BOT_TOKEN", "123:synthetic")
    assert send_telegram_message("@synthetic", "😀" * 2100).status == "failed"
