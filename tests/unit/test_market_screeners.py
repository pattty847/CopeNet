"""Synthetic behavior checks: coverage, eligibility, setup boundaries and admission."""
import asyncio
import math
from unittest.mock import patch

import pandas as pd
import pytest
from pydantic import ValidationError

from copenet.core.market.scans.screeners.models import MAX_ROWS, ScreenerConfig
from copenet.core.market.scans.screeners.source import FIELDS, fetch_snapshot, normalize
from copenet.core.market.scans.screeners.evaluate import evaluate
from copenet.core.market.scans.screeners.service import ScreenerService
from copenet.core.market.watchlist_store import WatchlistStore


def row(**changes):
    return {"id": "NYSE:TEST", "symbol": "TEST", "exchange": "NYSE", "name": "Synthetic Company", "sector": "Test",
            "type": "stock", "subtype": "common", "price": 100., "marketCap": 20e9, "averageVolume": 1e6,
            "relativeVolume": 2., "change": -3., "rsi": 50., "sma50": 99., "sma200": 90.,
            "high52": 106., "bandUpper": 103., "bandLower": 97., "monthReturn": -2.,
            "updateMode": "delayed_streaming_900", **changes}


def source(*rows):
    return {"rows": list(rows), "received": len(rows), "invalid": 0, "truncated": False}


def matches(result, identifier):
    return next(screen["rows"] for screen in result["screens"] if screen["id"] == identifier)


def test_common_shares_and_unknown_liquidity_do_not_get_guessed():
    result = evaluate(source(row(subtype="preferred"), row(averageVolume=None), row(averageVolume=1), row()), ScreenerConfig())
    assert result["eligible"] == 1
    assert result["excluded"] == {"instrument": 1, "missingEligibility": 1, "outsideUniverse": 1}


def test_setups_have_both_directions_and_exclude_extreme_spikes():
    result = evaluate(source(row(), row(id="NYSE:UP", symbol="UP", change=4), row(id="NYSE:SPIKE", change=90)), ScreenerConfig())
    assert [r["direction"] for r in matches(result, "expansion")] == ["Bearish", "Bullish"]
    assert matches(result, "pullback")
    assert matches(result, "compression")
    result = evaluate(source(row(price=80, sma50=85, sma200=90, rsi=35, high52=110)), ScreenerConfig())
    assert matches(result, "breakdown") and matches(result, "oversold")


def test_missing_technicals_do_not_exclude_other_screens():
    result = evaluate(source(row(bandUpper=None, rsi=None)), ScreenerConfig())
    assert not matches(result, "compression")
    assert matches(result, "expansion")
    assert result["screens"][0]["missingFields"] == 1


def test_boundary_keeps_class_shares_and_legitimate_suffixes():
    raw = {field.value[0]: None for field in FIELDS.values()}
    for symbol in ("NYSE:BRK.B", "NYSE:SNOW", "NASDAQ:BIDU"):
        parsed = normalize({**raw, "Symbol": symbol, "Price": math.nan})
        assert parsed is not None and parsed["price"] is None
    assert normalize({**raw, "Symbol": "OTC:TEST"}) is None
    assert normalize({**raw, "Symbol": "NYSE:BRK.B"})["symbol"] == "BRK-B"


def test_vendor_query_has_all_filters_and_detects_cap():
    columns = ["Symbol", *(field.value[0] for field in FIELDS.values())]
    frame = pd.DataFrame([["NYSE:TEST", *([None] * len(FIELDS))]], columns=columns)
    captured = []
    def get(query):
        captured.append(query._build_payload([]))
        return frame
    with patch("copenet.core.market.scans.screeners.source.StockScreener.get", get):
        result = fetch_snapshot(ScreenerConfig(maxCap=50e9))
    payload = captured[0]
    assert payload["range"] == [0, MAX_ROWS + 1]
    assert {f["left"] for f in payload["filter"]} >= {"type", "subtype", "exchange", "market_cap_basic", "close"}
    assert not result["truncated"]


@pytest.mark.parametrize("config", [{"minCap": 0}, {"maxCap": 1e9}, {"minPrice": float("nan")}, {"minDollarVolume": True}, {"extra": 1}])
def test_strict_universe_validation(config):
    with pytest.raises(ValidationError):
        ScreenerConfig.model_validate(config)


async def test_snapshot_failure_retains_previous_result_and_handoff_is_create_only(tmp_path):
    store = WatchlistStore(tmp_path / "watchlist.json")
    service = ScreenerService(tmp_path, store, fetch=lambda config: source(row()))
    config = ScreenerConfig()
    preview = service.preview(config)
    with pytest.raises(ValueError, match="Preview"):
        service.start(ScreenerConfig(minCap=30e9), preview["scopeToken"])
    service.start(config, preview["scopeToken"])
    await service.task
    run = service.get_run(service.state()["latest"]["id"])
    assert run["observations"][0]["id"] == "NYSE:TEST"
    assert service.get_run(run["id"]) == run
    service.handoff(run["id"], ["TEST"], "Research")
    assert store.state()["roles"]["Research"] == "context"
    assert store.state()["active"] == "Default"
    assert next(item for item in store.scan_lists() if item["name"] == "Research")["entries"] == [{"symbol": "TEST", "name": "Synthetic Company"}]
    with pytest.raises(ValueError, match="already exists"):
        service.handoff(run["id"], ["TEST"], "Research")
    with pytest.raises(ValueError, match="Select symbols"):
        service.handoff(run["id"], ["MISSING"], "Other")
    service.fetch = lambda config: (_ for _ in ()).throw(ValueError("Source unavailable"))
    service.start(config, service.preview(config)["scopeToken"])
    await service.task
    state = service.state()
    assert state["latest"]["id"] == run["id"]
    assert state["history"][0]["status"] == "error"
    with pytest.raises(ValueError, match="Preview"):
        service.start(config, preview["scopeToken"])


async def test_concurrent_run_is_rejected(tmp_path):
    release = asyncio.Event()
    service = ScreenerService(tmp_path, WatchlistStore(tmp_path / "watchlist.json"))
    service.task = asyncio.create_task(release.wait())
    config = ScreenerConfig()
    with pytest.raises(ValueError, match="already active"):
        service.start(config, service.preview(config)["scopeToken"])
    release.set()
    await service.task
