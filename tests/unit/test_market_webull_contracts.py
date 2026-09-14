"""Synthetic current-vendor contracts; no account construction or network access."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from copenet.core.market.webull import orders, sync
from copenet.core.market.webull.config import WebullConfig


def client_with_pages(*pages):
    client = SimpleNamespace(order_v3=SimpleNamespace(list_order_history=Mock()))
    client.order_v3.list_order_history.side_effect = [SimpleNamespace(json=lambda p=p: p) for p in pages]
    return client


def combo(identity, **fields):
    return {"orders": [{"order_id": identity, "symbol": "SYNTH", "side": "BUY", "instrument_type": "EQUITY",
                        "status": "FILLED", "filled_quantity": "1.23456", "filled_price": "25",
                        "filled_time_at": "2026-09-01T15:00:00.000Z", **fields}]}


def test_history_consumes_cursor_even_for_small_or_empty_pages(monkeypatch):
    monkeypatch.setattr(orders.time, "sleep", lambda _: None)
    first, last = combo("first"), combo("last")
    client = client_with_pages({"data": [first], "pagination_key": "next"},
                               {"data": [], "pagination_key": "final"}, {"data": [last]})
    assert orders.fetch_order_history(client, "synthetic") == [first, last]
    calls = client.order_v3.list_order_history.call_args_list
    assert calls[0].kwargs["start_time"] == "2018-05-21T00:00:00.000Z"
    assert calls[1].kwargs["pagination_key"] == "next"
    assert calls[2].kwargs["pagination_key"] == "final"
    assert calls[0].kwargs["end_time"] == calls[2].kwargs["end_time"]
    assert "page_size" not in calls[0].kwargs


@pytest.mark.parametrize("page", [[], {}, {"data": None}, {"data": [None]}, {"data": [{}]},
                                    {"data": [], "pagination_key": 12}])
def test_history_rejects_invalid_pages_without_replacing_saved_history(monkeypatch, page):
    save = Mock()
    monkeypatch.setattr(orders, "save_fills", save)
    with pytest.raises(ValueError):
        orders.sync_fills(client_with_pages(page), "synthetic")
    save.assert_not_called()


def test_history_rejects_repeated_cursor_and_page_limit(monkeypatch):
    monkeypatch.setattr(orders.time, "sleep", lambda _: None)
    page = {"data": [combo("same")], "pagination_key": "same"}
    with pytest.raises(ValueError, match="stalled"):
        orders.fetch_order_history(client_with_pages(page, page), "synthetic")
    monkeypatch.setattr(orders, "_MAX_PAGES", 1)
    with pytest.raises(ValueError, match="page limit"):
        orders.fetch_order_history(client_with_pages(page), "synthetic")


def test_history_retries_rate_limits(monkeypatch):
    pauses = []
    monkeypatch.setattr(orders.time, "sleep", pauses.append)
    client = client_with_pages()
    client.order_v3.list_order_history.side_effect = [RuntimeError("TOO_MANY_REQUESTS"),
                                                    SimpleNamespace(json=lambda: {"data": []})]
    assert orders.fetch_order_history(client, "synthetic") == []
    assert pauses == [5.0]


def test_fills_preserve_cancelled_and_partial_executions_and_deduplicate_order_ids():
    cancelled = combo("cancelled", status="CANCELLED")
    partial = combo("partial", status="PARTIAL_FILLED", filled_quantity="0.00001")
    fills, warnings = orders.normalize_fills([cancelled, partial, cancelled])
    assert len(fills) == 2
    assert fills[0].quantity == 1.23456
    assert fills[1].quantity == 0.00001
    assert warnings == []


def test_fills_reject_unknown_time_and_unsupported_instruments():
    fills, warnings = orders.normalize_fills([
        combo("time", filled_time_at=None, place_time_at="2026-08-01T12:00:00Z"),
        combo("future", instrument_type="FUTURES"),
        combo("nonfinite", filled_quantity="NaN"),
        combo("multileg", instrument_type="OPTION", legs=[{}, {}]),
    ])
    assert fills == []
    assert len(warnings) == 4


def test_snapshot_rejects_malformed_position_response_before_persisting(monkeypatch):
    save = Mock()
    monkeypatch.setattr(sync, "save_snapshot", save)
    client = SimpleNamespace(account_v2=SimpleNamespace(
        get_account_balance=lambda _: SimpleNamespace(json=lambda: {"total_net_liquidation_value": "100"}),
        get_account_position=lambda _: SimpleNamespace(json=lambda: {"error": "invalid"}),
    ))
    with pytest.raises(ValueError, match="invalid positions"):
        sync.fetch_snapshot(client, "synthetic")
    save.assert_not_called()


def test_non_equity_positions_do_not_use_underlying_equity_prices(monkeypatch):
    fetch = Mock(side_effect=AssertionError("must not fetch underlying price"))
    monkeypatch.setattr("copenet.core.market.data_sources.fetch_ohlcv", fetch)
    position = sync.WebullPosition("SYNTH", 1, avg_cost=2, last_price=3, asset_type="OPTION")
    sync.enrich_with_yfinance([position])
    sync.finalize([position], 100)
    assert position.unrealized_pl is None
    assert position.market_value is None
    fetch.assert_not_called()


def test_short_position_percentage_has_the_same_sign_as_dollar_pnl():
    position = sync.WebullPosition("SYNTH", -2, avg_cost=100, last_price=90, asset_type="EQUITY")
    sync.finalize([position], 1000)
    assert position.unrealized_pl == 20
    assert position.unrealized_pl_pct == 10


def test_sandbox_configuration_uses_current_vendor_host():
    assert WebullConfig("synthetic", "synthetic", env="sandbox").sandbox_host == "api.sandbox.webull.com"
    assert WebullConfig("synthetic", "synthetic").sandbox_host is None


def test_installed_sdk_uses_current_history_and_position_paths():
    from webull.trade.trade.v3.order_operation_v3 import OrderOperationV3
    from webull.trade.trade.v2.account_info_v2 import AccountV2

    transport = Mock()
    OrderOperationV3(transport).list_order_history("synthetic", pagination_key="cursor")
    request = transport.get_response.call_args.args[0]
    assert request.get_action_name() == "/trading/orders/historical-orders/list"
    assert request.get_headers()["x-version"] == "v3"
    assert request.get_query_params() == {"account_id": "synthetic", "pagination_key": "cursor"}
    AccountV2(transport).get_account_position("synthetic")
    request = transport.get_response.call_args.args[0]
    assert request.get_action_name() == "/trading/assets/positions/list"
