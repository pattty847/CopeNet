from __future__ import annotations

from pathlib import Path

import pytest

from copenet.core.market.alerts import PriceAlertStore, evaluate_price_alerts
from copenet.core.market.models import MarketBar
from copenet.core.market.price_history import SPLIT_ADJUSTED
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


def test_evaluator_reads_split_adjusted_daily_close_and_publishes_pulse(tmp_path: Path) -> None:
    alert_store = PriceAlertStore(tmp_path)
    alert_store.create(symbol="AAPL", direction="below", threshold=190, reference_price=195)

    class Prices:
        def refresh(self, symbol, *, max_age_seconds):
            assert (symbol, max_age_seconds) == ("AAPL", 60)

        def bars(self, symbol, *, timeframe, basis):
            assert (symbol, timeframe, basis) == ("AAPL", "daily", SPLIT_ADJUSTED)
            return [MarketBar(t=1, o=188, h=189, l=187, c=188, v=100)]

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
