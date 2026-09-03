from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone

import pytest

from copenet.core.market.alerts import PriceAlertStore, evaluate_price_alerts
from copenet.core.market.models import MarketBar
from copenet.core.market.price_cache import PriceHistory
from copenet.core.market.price_history import daily_close_available_at, utc_midnight
from copenet.core.market.store import MarketStore
from copenet.host import rpc_market_alerts


def test_price_alert_triggers_once_on_daily_close_crossing(tmp_path: Path) -> None:
    store = PriceAlertStore(tmp_path)
    alert = store.create(symbol="aapl", direction="above", threshold=200, reference_price=195)

    assert store.evaluate({"AAPL": 199}) == []
    triggered = store.evaluate({"AAPL": 201})
    assert [item.alert_id for item in triggered] == [alert.alert_id]
    assert triggered[0].status == "triggered"
    assert triggered[0].trigger_price == 201
    assert store.evaluate({"AAPL": 205}) == []

    events = (tmp_path / "alerts" / "events.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(events) == 1


def test_price_alert_cancel_preserves_rule_history(tmp_path: Path) -> None:
    store = PriceAlertStore(tmp_path)
    alert = store.create(symbol="SOFI", direction="below", threshold=12, reference_price=13)
    cancelled = store.cancel(alert.alert_id)
    assert cancelled.status == "cancelled"
    assert store.list(status="active") == []
    assert store.list()[0].status == "cancelled"


def test_price_alert_rejects_non_positive_prices(tmp_path: Path) -> None:
    store = PriceAlertStore(tmp_path)
    with pytest.raises(ValueError, match="positive"):
        store.create(symbol="AAPL", direction="above", threshold=0, reference_price=195)
    with pytest.raises(ValueError, match="positive"):
        store.create(symbol="AAPL", direction="above", threshold=float("nan"), reference_price=195)


def test_evaluator_reads_split_adjusted_daily_close_and_publishes_pulse(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("copenet.core.market.alerts._now_iso", lambda: "2026-01-05T12:00:00+00:00")
    alert_store = PriceAlertStore(tmp_path)
    alert_store.create(symbol="AAPL", direction="below", threshold=190, reference_price=195)

    class Prices:
        def refresh(self, symbol, *, max_age_seconds):
            assert (symbol, max_age_seconds) == ("AAPL", 60)
            bar = MarketBar(t=utc_midnight(datetime(2026, 1, 5).date()), o=188, h=189, l=187, c=188, v=100)
            return PriceHistory("AAPL", [bar], [], [], "2026-01-06T14:45:00+00:00")

    class PulseStore:
        def __init__(self):
            self.records = {}

        def get(self, pulse_id):
            return self.records.get(pulse_id)

        def create(self, record):
            self.records[record.pulse_id] = record

    runtime = type("Runtime", (), {"store": MarketStore(tmp_path), "prices": Prices()})()
    pulses = PulseStore()
    triggered = evaluate_price_alerts(runtime, pulses)
    assert triggered[0].trigger_price == 188
    assert next(iter(pulses.records.values())).title == "AAPL crossed below $190.00"


@pytest.mark.parametrize(("fetched", "created", "expected"), [
    ("2026-01-06T14:45:00+00:00", "2026-01-05T12:00:00+00:00", False),
    ("2026-01-06T20:59:00+00:00", "2026-01-05T12:00:00+00:00", False),
    ("2026-01-06T21:00:00+00:00", "2026-01-05T12:00:00+00:00", True),
    ("2026-01-06T14:45:00+00:00", "2026-01-06T14:30:00+00:00", False),
])
def test_daily_alert_ignores_forming_candle_and_never_fires_backwards(tmp_path, monkeypatch, fetched, created, expected):
    monkeypatch.setattr("copenet.core.market.alerts._now_iso", lambda: created)
    store = PriceAlertStore(tmp_path)
    store.create(symbol="TEST", direction="above", threshold=105, reference_price=100)
    bars = [
        MarketBar(t=utc_midnight(datetime(2026, 1, day).date()), o=price, h=price, l=price, c=price, v=100)
        for day, price in [(5, 100), (6, 110)]
    ]
    history = PriceHistory("TEST", bars, [], [], fetched)
    prices = type("Prices", (), {"refresh": lambda self, *a, **kw: history})()
    runtime = type("Runtime", (), {"store": MarketStore(tmp_path), "prices": prices})()
    assert bool(evaluate_price_alerts(runtime)) == expected
    if created.startswith("2026-01-06"):
        assert store.list()[0].last_evaluated_at is None


@pytest.mark.parametrize(("day", "utc_hour"), [("2026-01-05", 21), ("2026-08-03", 20)])
def test_daily_close_availability_observes_new_york_dst(day, utc_hour):
    bar = MarketBar(t=utc_midnight(datetime.fromisoformat(day).date()), o=1, h=1, l=1, c=1, v=1)
    assert daily_close_available_at(bar).astimezone(timezone.utc).hour == utc_hour


@pytest.mark.asyncio
async def test_alert_rpc_create_list_and_cancel(tmp_path: Path) -> None:
    orchestrator = type("Orchestrator", (), {"market_store": MarketStore(tmp_path)})()
    sent = []

    async def send_json(payload):
        sent.append(payload)

    await rpc_market_alerts.handle_market_alerts_create(
        "create",
        {"symbol": "aapl", "direction": "above", "threshold": 200, "referencePrice": 195},
        send_json,
        orchestrator,
    )
    alert = sent[-1]["payload"]["alerts"][0]
    assert alert["evaluationBasis"] == "daily_close"

    await rpc_market_alerts.handle_market_alerts_list("list", {"symbol": "AAPL"}, send_json, orchestrator)
    assert sent[-1]["payload"]["alerts"][0]["alertId"] == alert["alertId"]

    await rpc_market_alerts.handle_market_alerts_cancel(
        "cancel",
        {"alertId": alert["alertId"], "symbol": "AAPL"},
        send_json,
        orchestrator,
    )
    assert sent[-1]["payload"]["alerts"] == []
