"""Unit tests for the Webull fill-history → all-time P&L lane (no network, no SDK)."""

from __future__ import annotations

from datetime import date

from copenet.core.market.watchlist_store import WatchlistStore
from copenet.core.market.webull.orders import normalize_fills
from copenet.core.market.webull.pnl import build_ledger, reconcile, replay
from copenet.core.market.webull.watchlists import import_into_store


def _combo(symbol, side, qty, price, filled_at, status="FILLED", **extra):
    order = {
        "symbol": symbol,
        "side": side,
        "status": status,
        "order_id": f"{symbol}-{side}-{filled_at}",
        "instrument_type": extra.pop("instrument_type", "EQUITY"),
        "filled_quantity": str(qty),
        "filled_price": None if price is None else str(price),
        "filled_time_at": filled_at,
        "order_type": "LIMIT",
        **extra,
    }
    return {"client_order_id": order["order_id"], "orders": [order]}


def _fills(*combos):
    fills, warnings = normalize_fills(list(combos))
    return [f.to_dict() for f in fills], warnings


def test_normalize_fills_keeps_only_executed_orders_oldest_first():
    fills, warnings = _fills(
        _combo("AAPL", "BUY", 10, 100, "2026-02-01T15:00:00Z"),
        _combo("AAPL", "BUY", 5, 90, "2026-01-01T15:00:00Z"),
        _combo("AAPL", "BUY", 3, 80, "2026-03-01T15:00:00Z", status="CANCELLED"),
    )
    assert [f["filled_at"] for f in fills] == ["2026-01-01T15:00:00Z", "2026-02-01T15:00:00Z"]
    assert warnings == []


def test_normalize_fills_gives_options_a_contract_identity_and_multiplier():
    option_leg = {
        "instrument_type": "OPTION",
        "legs": [{"option_type": "CALL", "option_expire_date": "2026-07-26", "strike_price": "25.00"}],
    }
    fills, _ = _fills(_combo("BITO", "BUY", 1, 1.0, "2026-06-20T13:47:05Z", **option_leg))
    assert fills[0]["contract_key"] == "BITO 2026-07-26 25C"
    assert fills[0]["multiplier"] == 100.0
    assert fills[0]["symbol"] == "BITO"


def test_replay_matches_fifo_and_leaves_the_remainder_open():
    fills, _ = _fills(
        _combo("VTI", "BUY", 10, 100, "2026-01-01T15:00:00Z"),
        _combo("VTI", "BUY", 10, 120, "2026-02-01T15:00:00Z"),
        _combo("VTI", "SELL", 15, 130, "2026-03-01T15:00:00Z"),
    )
    trades, open_lots, warnings = replay(fills)
    # first lot closes whole (+$300), second closes 5 of 10 (+$50)
    assert [round(t.pnl, 2) for t in trades] == [300.0, 50.0]
    assert len(open_lots) == 1
    assert open_lots[0].quantity == 5
    assert open_lots[0].price == 120
    assert warnings == []


def test_reverse_split_restates_open_lots_before_matching():
    """A synthetic reverse split must restate open lots before FIFO matching."""
    fills, _ = _fills(
        _combo("REVERSE", "BUY", 100, 10, "2025-01-01T15:00:00Z"),
        _combo("REVERSE", "SELL", 10, 50, "2025-02-02T15:00:00Z"),
    )
    splits = {"REVERSE": [["2025-02-01", 0.1]]}

    unadjusted, _, _ = replay(fills)
    adjusted, open_lots, _ = replay(fills, splits)

    assert unadjusted[0].pnl > 0  # the wrong answer, kept here so the regression is unmistakable
    assert adjusted[0].entry_price == 100.0
    assert adjusted[0].pnl == -500.0
    assert sum(lot.quantity for lot in open_lots) == 0


def test_split_does_not_touch_lots_opened_on_or_after_the_ex_date():
    """Synthetic lots opened on or after the ex-date already use post-split units."""
    fills, _ = _fills(
        _combo("SPLIT", "BUY", 1, 50, "2025-12-05T15:00:00Z"),
        _combo("SPLIT", "BUY", 1, 49, "2025-12-23T15:00:00Z"),
    )
    _, open_lots, _ = replay(fills, {"SPLIT": [["2025-12-05", 2.0]]})
    assert sum(lot.quantity for lot in open_lots) == 2


def test_vanished_position_writes_off_its_remaining_basis():
    fills, _ = _fills(_combo("MNMD", "BUY", 84, 3.36, "2021-06-14T15:00:00Z"))
    ledger = build_ledger(
        {"fills": fills, "synced_at": "x", "history_start": "2016-01-01", "splits": {}},
        {"positions": []},
        today=date(2026, 7, 1),
    )
    assert ledger is not None
    assert ledger.unaccounted_position_pl == -282.24  # 84 * 3.36
    assert ledger.all_time_pnl == -282.24
    assert any("left the account with no sell order" in caveat for caveat in ledger.caveats)
    assert [row.symbol for row in ledger.reconciliation] == ["MNMD"]  # drift still shown, not hidden


def test_partial_quantity_drift_is_reported_but_never_assumed():
    """A symbol the broker still holds at a different size stays untouched — only fully-vanished
    positions are written off."""
    fills, _ = _fills(_combo("SLI", "BUY", 29, 4.13, "2026-01-02T15:00:00Z"))
    ledger = build_ledger(
        {"fills": fills, "synced_at": "x", "history_start": "2016-01-01", "splits": {}},
        {"positions": [{"symbol": "SLI", "quantity": 20, "unrealized_pl": -10.0}]},
        today=date(2026, 7, 1),
    )
    assert ledger is not None
    assert ledger.unaccounted_position_pl == 0.0
    assert [row.symbol for row in ledger.reconciliation] == ["SLI"]


def test_replay_handles_a_short_round_trip():
    fills, _ = _fills(
        _combo("TSLA", "SELL", 2, 300, "2026-01-01T15:00:00Z"),
        _combo("TSLA", "BUY", 2, 250, "2026-02-01T15:00:00Z"),
    )
    trades, open_lots, _ = replay(fills)
    assert [t.direction for t in trades] == ["short"]
    assert trades[0].pnl == 100.0  # sold high, bought back low
    assert open_lots == []


def test_replay_reports_unpriced_fills_instead_of_silently_dropping_them():
    fills, _ = _fills(
        _combo("MARK", "BUY", 1, None, "2020-06-18T18:53:06Z"),
        _combo("MARK", "SELL", 1, 2.0, "2020-06-19T18:53:06Z"),
    )
    trades, _, warnings = replay(fills)
    assert trades == []
    assert warnings and "no execution price" in warnings[0]


def test_expired_option_lot_counts_as_a_total_loss_of_premium():
    option_leg = {
        "instrument_type": "OPTION",
        "legs": [{"option_type": "CALL", "option_expire_date": "2026-07-26", "strike_price": "25.00"}],
    }
    fills, _ = _fills(_combo("BITO", "BUY", 1, 1.0, "2026-06-20T13:47:05Z", **option_leg))
    ledger = build_ledger({"fills": fills, "synced_at": "x", "history_start": "2016-01-01", "splits": {}}, None, today=date(2026, 8, 1))
    assert ledger is not None
    assert ledger.expired_option_pl == -100.0  # 1 contract * $1.00 * 100
    assert ledger.all_time_pnl == -100.0
    assert any("expired without a closing trade" in caveat for caveat in ledger.caveats)


def test_ledger_combines_realized_with_broker_unrealized():
    fills, _ = _fills(
        _combo("VTI", "BUY", 10, 100, "2026-01-01T15:00:00Z"),
        _combo("VTI", "SELL", 10, 110, "2026-02-01T15:00:00Z"),
        _combo("XLK", "BUY", 5, 150, "2026-03-01T15:00:00Z"),
    )
    snapshot = {"positions": [{"symbol": "XLK", "quantity": 5, "unrealized_pl": 175.5}]}
    ledger = build_ledger({"fills": fills, "synced_at": "x", "history_start": "2016-01-01", "splits": {}}, snapshot, today=date(2026, 7, 1))
    assert ledger is not None
    assert ledger.realized_pnl == 100.0
    assert ledger.unrealized_pnl == 175.5
    assert ledger.all_time_pnl == 275.5
    assert ledger.win_rate_pct == 100.0
    assert {row.symbol for row in ledger.by_symbol} == {"VTI", "XLK"}
    assert ledger.reconciliation == []  # replay and broker agree on XLK


def test_reconcile_surfaces_shares_that_left_without_a_sell_order():
    fills, _ = _fills(_combo("MNMD", "BUY", 84, 5, "2026-01-01T15:00:00Z"))
    _, open_lots, _ = replay(fills)
    rows = reconcile(open_lots, {"positions": []})
    assert [row.symbol for row in rows] == ["MNMD"]
    assert rows[0].replayed_quantity == 84
    assert rows[0].broker_quantity is None


def test_build_ledger_returns_none_without_history():
    assert build_ledger(None, None) is None
    assert build_ledger({"fills": []}, None) is None


def test_watchlist_import_upserts_by_name_and_leaves_other_lists_alone(tmp_path):
    store = WatchlistStore(tmp_path / "watchlist.json")
    store.create_list("Sectors")
    store.add("XLK", "Technology", "Sectors")
    store.replace_list("AI", [{"symbol": "nvda", "name": "Nvidia"}])

    result = import_into_store(store, [{"name": "AI", "symbols": [{"symbol": "GOOG", "name": "Alphabet"}]}])

    assert result["imported"] == [{"name": "AI", "count": 1}]
    assert [e["symbol"] for e in store.list("AI")] == ["GOOG"]  # replaced, not appended
    assert [e["symbol"] for e in store.list("Sectors")] == ["XLK"]  # untouched
