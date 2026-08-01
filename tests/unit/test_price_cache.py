"""Behavioral contracts for the durable daily price cache.

The load-bearing rule under test: dividends never invalidate the cache, splits always do.
Everything else here exists so the cache cannot quietly turn into the thing it replaced —
a network call on every read.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from copenet.core.market.price_cache import PriceCache
from copenet.core.market.price_history import TOTAL_RETURN, WEEKLY, bar_date


def frame(days: list[str], *, close: float = 100.0) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.to_datetime(days),
            "open": [close] * len(days),
            "high": [close] * len(days),
            "low": [close] * len(days),
            "close": [close] * len(days),
            "volume": [1_000] * len(days),
        }
    )


class RecordingFetch:
    """Stands in for yfinance and records exactly what was asked for."""

    def __init__(self, responses: dict[str, tuple]) -> None:
        self.responses = responses
        self.calls: list[str] = []

    def __call__(self, symbol: str, *, period: str = "max"):
        self.calls.append(period)
        return self.responses[period]


def test_first_refresh_pulls_full_history_and_serves_later_reads_from_disk(tmp_path) -> None:
    fetch = RecordingFetch({"max": (frame(["2026-03-02", "2026-03-03"]), [], [])})
    cache = PriceCache(tmp_path, fetch=fetch)

    cache.refresh("AAPL")

    assert fetch.calls == ["max"]
    # A read must never reach the network. This is the whole point of the cache.
    assert len(cache.bars("AAPL")) == 2
    assert fetch.calls == ["max"]


def test_a_fresh_cache_skips_the_network_entirely(tmp_path) -> None:
    fetch = RecordingFetch(
        {
            "max": (frame(["2026-03-02"]), [], []),
            "6mo": (frame(["2026-03-03"]), [], []),
        }
    )
    cache = PriceCache(tmp_path, fetch=fetch)
    cache.refresh("AAPL")

    cache.refresh("AAPL", max_age_seconds=3600)

    assert fetch.calls == ["max"]


def test_a_stale_cache_delta_fetches_instead_of_rebuilding(tmp_path) -> None:
    fetch = RecordingFetch(
        {
            "max": (frame(["2026-03-02", "2026-03-03"]), [], []),
            "6mo": (frame(["2026-03-04"]), [], []),
        }
    )
    cache = PriceCache(tmp_path, fetch=fetch)
    cache.refresh("AAPL", now=datetime(2026, 3, 3, tzinfo=timezone.utc))

    cache.refresh("AAPL", now=datetime(2026, 3, 4, tzinfo=timezone.utc))

    assert fetch.calls == ["max", "6mo"]
    assert len(cache.bars("AAPL")) == 3


def test_a_delta_fetch_overwrites_the_provisional_current_bar(tmp_path) -> None:
    fetch = RecordingFetch(
        {
            "max": (frame(["2026-03-02"], close=100.0), [], []),
            # Same day, later in the session: the current candle is still moving.
            "6mo": (frame(["2026-03-02"], close=115.0), [], []),
        }
    )
    cache = PriceCache(tmp_path, fetch=fetch)
    cache.refresh("AAPL", now=datetime(2026, 3, 2, 15, tzinfo=timezone.utc))

    cache.refresh("AAPL", now=datetime(2026, 3, 2, 20, tzinfo=timezone.utc))

    bars = cache.bars("AAPL")
    assert len(bars) == 1
    assert bars[0].c == 115.0


def test_a_new_dividend_does_not_invalidate_stored_history(tmp_path) -> None:
    fetch = RecordingFetch(
        {
            "max": (frame(["2026-03-02", "2026-03-03"]), [], []),
            "6mo": (frame(["2026-03-04"]), [], [("2026-03-04", 0.25)]),
        }
    )
    cache = PriceCache(tmp_path, fetch=fetch)
    cache.refresh("AAPL", now=datetime(2026, 3, 3, tzinfo=timezone.utc))

    cache.refresh("AAPL", now=datetime(2026, 3, 4, tzinfo=timezone.utc))

    # Delta only — a dividend shifts derived total-return prices, never stored ones.
    assert fetch.calls == ["max", "6mo"]
    history = cache.load("AAPL")
    assert history is not None
    assert history.dividends == [("2026-03-04", 0.25)]
    assert [row.c for row in history.bars] == [100.0, 100.0, 100.0]


def test_a_new_split_forces_a_full_rebuild(tmp_path) -> None:
    fetch = RecordingFetch(
        {
            # Seed a cache from before the split: unsplit prices, no split recorded.
            "max": (frame(["2026-03-02", "2026-03-03"], close=100.0), [], []),
            "6mo": (frame(["2026-03-04"], close=25.0), [("2026-03-04", 4.0)], []),
        }
    )
    cache = PriceCache(tmp_path, fetch=fetch)
    cache.refresh("AAPL", now=datetime(2026, 3, 3, tzinfo=timezone.utc))
    # Yahoo has now rewritten the whole symbol onto the post-split basis.
    fetch.responses["max"] = (
        frame(["2026-03-02", "2026-03-03", "2026-03-04"], close=25.0),
        [("2026-03-04", 4.0)],
        [],
    )
    fetch.calls.clear()

    cache.refresh("AAPL", now=datetime(2026, 3, 4, tzinfo=timezone.utc))

    # The delta call discovers the split, then the whole symbol is re-pulled. Merging
    # would glue pre-split and post-split prices together — the exact corruption the
    # auto_adjust invariant exists to prevent.
    assert fetch.calls == ["6mo", "max"]
    assert [row.c for row in cache.bars("AAPL")] == [25.0, 25.0, 25.0]


def test_an_already_known_split_does_not_trigger_a_rebuild(tmp_path) -> None:
    fetch = RecordingFetch(
        {
            "max": (frame(["2026-03-02", "2026-03-03"]), [("2026-03-02", 4.0)], []),
            "6mo": (frame(["2026-03-04"]), [("2026-03-02", 4.0)], []),
        }
    )
    cache = PriceCache(tmp_path, fetch=fetch)
    cache.refresh("AAPL", now=datetime(2026, 3, 3, tzinfo=timezone.utc))

    cache.refresh("AAPL", now=datetime(2026, 3, 4, tzinfo=timezone.utc))

    assert fetch.calls == ["max", "6mo"]


def test_a_failed_fetch_returns_none_rather_than_an_empty_history(tmp_path) -> None:
    fetch = RecordingFetch({"max": (frame([]), [], [])})
    cache = PriceCache(tmp_path, fetch=fetch)

    # "No data" must stay distinguishable from "this symbol has no history".
    assert cache.refresh("NOPE") is None
    assert cache.bars("NOPE") == []


def test_a_failed_delta_fetch_keeps_serving_the_existing_cache(tmp_path) -> None:
    fetch = RecordingFetch(
        {
            "max": (frame(["2026-03-02", "2026-03-03"]), [], []),
            "6mo": (frame([]), [], []),
        }
    )
    cache = PriceCache(tmp_path, fetch=fetch)
    cache.refresh("AAPL", now=datetime(2026, 3, 3, tzinfo=timezone.utc))

    history = cache.refresh("AAPL", now=datetime(2026, 3, 4, tzinfo=timezone.utc))

    assert history is not None
    assert len(history.bars) == 2


def test_cached_dailies_serve_every_timeframe_and_basis_without_refetching(tmp_path) -> None:
    fetch = RecordingFetch(
        {
            "max": (
                frame(["2026-03-02", "2026-03-03", "2026-03-09"], close=100.0),
                [],
                [("2026-03-03", 5.0)],
            )
        }
    )
    cache = PriceCache(tmp_path, fetch=fetch)
    cache.refresh("AAPL")

    weekly = cache.bars("AAPL", timeframe=WEEKLY)
    total_return = cache.bars("AAPL", basis=TOTAL_RETURN)

    # One download backs daily, weekly, monthly, split-only and total-return.
    assert fetch.calls == ["max"]
    assert [str(bar_date(row)) for row in weekly] == ["2026-03-02", "2026-03-09"]
    assert total_return[0].c == pytest.approx(95.0)


def test_a_cache_written_by_an_older_version_is_ignored(tmp_path) -> None:
    fetch = RecordingFetch({"max": (frame(["2026-03-02"]), [], [])})
    cache = PriceCache(tmp_path, fetch=fetch)
    cache.refresh("AAPL")
    path = tmp_path / "AAPL.json"
    path.write_text(path.read_text().replace('"cacheVersion": 1', '"cacheVersion": 0'))

    # A stale schema must read as "nothing cached", not as corrupt bars.
    assert cache.load("AAPL") is None


def test_blank_symbols_are_rejected(tmp_path) -> None:
    with pytest.raises(ValueError):
        PriceCache(tmp_path, fetch=RecordingFetch({})).refresh("   ")
