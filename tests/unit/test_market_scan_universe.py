"""The scan universe: public UNIVERSE + the operator's watchlists.

Regression cover for fca5acb, which moved personal holdings out of `universe.py` (correctly —
they are operator data) without re-sourcing them at refresh time. `live_signal_symbols` then
resolved to `[]`, and the accumulation / trend / soft-bottoming / speculative panels and the
SEC evidence sweep all computed over an empty set and rendered empty for four days.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from copenet.core.market.brief import compute_movers
from copenet.core.market.models import MarketBar
from copenet.core.market.store import MarketStore
from copenet.core.market.runtime import _symbols_for_scope
from copenet.core.market.universe import (
    INDUSTRY_SYMBOLS,
    MACRO_SYMBOLS,
    SECTOR_SYMBOLS,
    SIGNAL_ROLES,
    UNIVERSE,
    merge_watchlist_assets,
    yf_symbol,
)
from copenet.core.market.watchlist_store import WatchlistStore


def _write(path: Path, lists: list[dict]) -> WatchlistStore:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"lists": lists, "active": lists[0]["name"]}), encoding="utf-8")
    return WatchlistStore(path)


# ---------- merge_watchlist_assets ----------


def test_watchlist_symbols_rejoin_the_scan_with_a_signal_role() -> None:
    """The core regression: without this, every per-name signal panel computes over nothing."""
    assets = merge_watchlist_assets([{"name": "Mine", "role": "holding", "entries": [{"symbol": "SOFI", "name": "SoFi"}]}])
    sofi = next(a for a in assets if a.symbol == "SOFI")
    assert sofi.role == "holding"
    assert sofi.role in SIGNAL_ROLES
    assert [a.symbol for a in assets if a.role in SIGNAL_ROLES] == ["SOFI"]


def test_public_universe_wins_on_conflict_so_breadth_is_not_double_counted() -> None:
    """XLK is already a sector asset; a watchlist copy must not add a second XLK row."""
    assets = merge_watchlist_assets([{"name": "Sectors", "role": "watch", "entries": [{"symbol": "XLK"}]}])
    assert [a.symbol for a in assets].count("XLK") == 1
    assert next(a for a in assets if a.symbol == "XLK").role == "sector"
    assert len(assets) == len(UNIVERSE)


def test_context_role_keeps_a_list_out_of_the_signal_panels() -> None:
    """The opt-out: quoted in the watchlist UI, absent from breadth and the SEC sweep."""
    assets = merge_watchlist_assets([{"name": "Crypto ETFs", "role": "context", "entries": [{"symbol": "IBIT"}]}])
    ibit = next(a for a in assets if a.symbol == "IBIT")
    assert ibit.role == "context"
    assert ibit.role not in SIGNAL_ROLES


def test_unknown_and_missing_roles_default_to_watch() -> None:
    """A pre-roles watchlist file must scan, not silently sit out."""
    assets = merge_watchlist_assets(
        [
            {"name": "Old", "entries": [{"symbol": "AAA"}]},
            {"name": "Typo", "role": "holdings", "entries": [{"symbol": "BBB"}]},
        ]
    )
    assert {a.symbol: a.role for a in assets if a.symbol in {"AAA", "BBB"}} == {"AAA": "watch", "BBB": "watch"}


def test_a_signal_role_beats_context_regardless_of_list_order() -> None:
    """A ticker parked in an old broker import must not shadow the curated scan list.

    Regression: ordering used to decide this, so 13 pre-existing `context` lists sitting
    earlier in the file silently claimed a third of a freshly built scan list.
    """
    assets = merge_watchlist_assets(
        [
            {"name": "Old Webull Import", "role": "context", "entries": [{"symbol": "AAPL"}]},
            {"name": "Scan", "role": "watch", "entries": [{"symbol": "AAPL"}]},
        ]
    )
    aapl = [a for a in assets if a.symbol == "AAPL"]
    assert len(aapl) == 1
    assert aapl[0].role == "watch"


def test_first_list_still_wins_between_two_signal_roles() -> None:
    assets = merge_watchlist_assets(
        [
            {"name": "Positions", "role": "holding", "entries": [{"symbol": "GOOG"}]},
            {"name": "Scan", "role": "watch", "entries": [{"symbol": "GOOG"}]},
        ]
    )
    assert next(a for a in assets if a.symbol == "GOOG").role == "holding"


def test_duplicate_symbol_across_lists_is_added_once() -> None:
    assets = merge_watchlist_assets(
        [
            {"name": "A", "role": "holding", "entries": [{"symbol": "NVDA"}]},
            {"name": "B", "role": "watch", "entries": [{"symbol": "NVDA"}]},
        ]
    )
    nvda = [a for a in assets if a.symbol == "NVDA"]
    assert len(nvda) == 1
    assert nvda[0].role == "holding"  # first list wins


@pytest.mark.parametrize("lists", [None, [], [{"name": "Empty", "entries": []}], ["not-a-dict"]])
def test_degrades_to_the_public_universe(lists) -> None:
    assert merge_watchlist_assets(lists) == UNIVERSE


def test_entry_without_a_symbol_is_skipped() -> None:
    assets = merge_watchlist_assets([{"name": "A", "entries": [{"name": "no symbol"}, {"symbol": "  "}, "junk"]}])
    assert assets == UNIVERSE


def test_symbols_are_normalized_to_uppercase() -> None:
    assets = merge_watchlist_assets([{"name": "A", "entries": [{"symbol": " sofi "}]}])
    assert any(a.symbol == "SOFI" for a in assets)


# ---------- WatchlistStore roles ----------


def test_role_round_trips_and_defaults_to_watch(tmp_path: Path) -> None:
    store = _write(tmp_path / "watchlist.json", [{"name": "Default", "entries": [{"symbol": "AAPL"}]}])
    assert store.scan_lists()[0]["role"] == "watch"
    store.set_list_role("Default", "holding")
    assert store.scan_lists()[0]["role"] == "holding"
    assert store.state()["roles"] == {"Default": "holding"}


def test_set_list_role_rejects_an_unknown_role(tmp_path: Path) -> None:
    store = _write(tmp_path / "watchlist.json", [{"name": "Default", "entries": []}])
    with pytest.raises(ValueError, match="role must be one of"):
        store.set_list_role("Default", "nonsense")


def test_replace_list_preserves_an_operator_set_role(tmp_path: Path) -> None:
    """A Webull re-import owns the entries; it must not silently drop the list out of the scan."""
    store = _write(tmp_path / "watchlist.json", [{"name": "Broker", "role": "holding", "entries": [{"symbol": "OLD"}]}])
    store.replace_list("Broker", [{"symbol": "NEW", "name": "New"}])
    scanned = store.scan_lists()[0]
    assert scanned["role"] == "holding"
    assert [e["symbol"] for e in scanned["entries"]] == ["NEW"]


# ---------- scan scope ----------


def test_context_symbols_are_not_swept() -> None:
    """Quoted, never analyzed — sweeping them daily buys nothing and dominates the request budget."""
    universe = merge_watchlist_assets(
        [
            {"name": "Scan", "role": "watch", "entries": [{"symbol": "NVDA"}]},
            {"name": "Old Import", "role": "context", "entries": [{"symbol": "ZZZZ"}]},
        ]
    )
    symbols = _symbols_for_scope("all", universe)
    assert "NVDA" in symbols
    assert "ZZZZ" not in symbols
    assert "VOO" in symbols  # public universe still swept in full


def test_industry_symbols_are_distinct_from_sector_symbols() -> None:
    """research_lab/benchmarks.py maps a stock to its sector ETF from SECTOR_SYMBOLS —
    an industry fund is not a sector benchmark and must not leak into that tuple."""
    assert not set(INDUSTRY_SYMBOLS) & set(SECTOR_SYMBOLS)
    by_symbol = {a.symbol: a.role for a in UNIVERSE}
    assert all(by_symbol[s] == "industry" for s in INDUSTRY_SYMBOLS)
    assert all(by_symbol[s] == "sector" for s in SECTOR_SYMBOLS)


def test_no_universe_role_earns_signal_work() -> None:
    """Bonds, gold and index ETFs in an equity breadth reading would make it meaningless."""
    assert not [a for a in UNIVERSE if a.role in SIGNAL_ROLES]


def test_every_macro_panel_symbol_exists_in_the_universe() -> None:
    """MACRO_SYMBOLS drives the macro strip by lookup — a typo renders as a silently missing tile."""
    known = {a.symbol for a in UNIVERSE}
    assert set(MACRO_SYMBOLS) <= known
    assert set(SECTOR_SYMBOLS) <= known
    assert set(INDUSTRY_SYMBOLS) <= known


def test_symbols_needing_a_provider_prefix_are_mapped() -> None:
    """An unmapped caret symbol is passed through verbatim and silently returns no data."""
    assert yf_symbol("TNX") == "^TNX"
    assert yf_symbol("VIX") == "^VIX"
    assert yf_symbol("NVDA") == "NVDA"


# ---------- compute_movers ----------


def test_movers_rank_watchlist_names_not_just_index_etfs(tmp_path: Path) -> None:
    """With the default universe this returns nothing but ETFs — which reads as a quiet tape."""
    store = MarketStore(tmp_path / "market")
    store.save_bars(
        "SOFI",
        "daily",
        [MarketBar(t=1, o=1, h=1, l=1, c=100.0, v=1), MarketBar(t=2, o=1, h=1, l=1, c=120.0, v=1)],
    )
    universe = merge_watchlist_assets([{"name": "Mine", "role": "holding", "entries": [{"symbol": "SOFI"}]}])

    assert compute_movers(store)[0] == []
    rows, _ = compute_movers(store, universe=universe)
    assert [r["symbol"] for r in rows] == ["SOFI"]
