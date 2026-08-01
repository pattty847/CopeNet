"""Behavioral contracts for cache-backed watchlist quotes.

The watchlist panel used to fan one yfinance download per symbol out simultaneously on
every load. A burst is the traffic shape that actually gets rate-limited, and unlike the
daily universe sweep it repeated on every render.
"""

from __future__ import annotations

import pandas as pd
import pytest

from copenet.core.market.price_cache import PriceCache
from copenet.core.market.quotes import (
    MAX_CONCURRENT_QUOTE_REFRESHES,
    quote_row,
    quote_rows,
)


def _history(closes: list[float], *, dividends: list[tuple[str, float]] | None = None):
    days = pd.bdate_range("2026-01-05", periods=len(closes))

    def fetch(_symbol: str, *, period: str = "max"):
        return (
            pd.DataFrame(
                {
                    "date": days,
                    "open": closes,
                    "high": closes,
                    "low": closes,
                    "close": closes,
                    "volume": [100] * len(closes),
                }
            ),
            [],
            dividends or [],
        )

    return fetch


def test_a_warm_watchlist_costs_no_requests(tmp_path) -> None:
    calls: list[str] = []
    inner = _history([10.0, 11.0])

    def counting(symbol: str, *, period: str = "max"):
        calls.append(period)
        return inner(symbol, period=period)

    cache = PriceCache(tmp_path, fetch=counting)

    quote_row(cache, "MSFT")
    quote_row(cache, "MSFT")
    quote_row(cache, "MSFT")

    # Rendering the panel repeatedly must not re-hit Yahoo once per render.
    assert calls == ["max"]


def test_cold_quote_fetches_are_bounded_not_fanned_out(tmp_path) -> None:
    """Twenty watchlist symbols must not mean twenty simultaneous requests."""
    live = 0
    peak = 0
    inner = _history([10.0, 11.0])

    def tracking(symbol: str, *, period: str = "max"):
        nonlocal live, peak
        live += 1
        peak = max(peak, live)
        try:
            return inner(symbol, period=period)
        finally:
            live -= 1

    cache = PriceCache(tmp_path, fetch=tracking)
    symbols = [f"SYM{index}" for index in range(20)]

    import asyncio

    rows = asyncio.run(quote_rows(cache, symbols))

    assert set(rows) == set(symbols)
    assert peak <= MAX_CONCURRENT_QUOTE_REFRESHES


def test_quote_uses_the_traded_price_not_a_total_return_series(tmp_path) -> None:
    """A watchlist shows what the stock costs, so a dividend must not move the day change."""
    cache = PriceCache(tmp_path, fetch=_history([100.0, 100.0], dividends=[("2026-01-06", 5.0)]))

    row = quote_row(cache, "KO")

    assert row is not None
    # Total-return would have back-shifted the earlier bar to 95 and reported +5.26%.
    assert row.change == "+0.00%"
    assert row.value == "$100.00"


def test_a_symbol_that_never_resolves_returns_none(tmp_path) -> None:
    def empty(_symbol: str, *, period: str = "max"):
        return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"]), [], []

    cache = PriceCache(tmp_path, fetch=empty)

    # This is what rejects an unknown ticker on add — it must stay distinguishable
    # from a real symbol with a quiet day.
    assert quote_row(cache, "ZZZZ") is None


def test_a_fetch_failure_degrades_to_the_cached_row(tmp_path) -> None:
    cache = PriceCache(tmp_path, fetch=_history([10.0, 12.0]))
    quote_row(cache, "MSFT")

    def exploding(_symbol: str, *, period: str = "max"):
        raise RuntimeError("simulated outage")

    cache._fetch = exploding
    row = quote_row(cache, "MSFT", max_age_seconds=0)

    assert row is not None
    assert row.value == "$12.00"
