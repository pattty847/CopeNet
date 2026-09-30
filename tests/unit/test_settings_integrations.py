"""Settings reports which integrations are configured, never the credential itself."""

import json

from copenet.core.settings.integrations import integration_statuses

_ENV = ["FRED_API_KEY", "TRADING_ECONOMICS_API_KEY", "WEBULL_KEY", "WEBULL_SECRET", "COPNET_TELEGRAM_BOT_TOKEN", "NASA_API_KEY"]


def _by_id(statuses):
    return {status.id: status for status in statuses}


def test_integration_reads_missing_keys_as_not_ready(monkeypatch):
    for name in _ENV:
        monkeypatch.delenv(name, raising=False)
    statuses = _by_id(integration_statuses())
    for integration_id in ("fred", "trading-economics", "webull", "telegram", "nasa"):
        assert statuses[integration_id].ready is False
    assert statuses["fred"].setup == "FRED_API_KEY"


def test_integration_status_never_carries_the_secret_value(monkeypatch):
    secret = "sk-very-private-value-123"
    for name in _ENV:
        monkeypatch.setenv(name, secret)
    statuses = integration_statuses()
    assert all(status.ready for status in statuses if status.id != "sec")
    assert secret not in json.dumps([status.to_public_dict() for status in statuses])


def test_webull_needs_both_key_and_secret(monkeypatch):
    monkeypatch.setenv("WEBULL_KEY", "key")
    monkeypatch.delenv("WEBULL_SECRET", raising=False)
    assert _by_id(integration_statuses())["webull"].ready is False
