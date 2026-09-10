"""The intraday bar lane: interval algebra, session-anchored resampling, and the store.

Offline by construction — nothing here touches the network. The vendor ceilings these rules
encode were measured on 2026-09-09 and are recorded in `docs/plans/INTRADAY_BARS.md`.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from copenet.core.market.intraday.fetch import _windows
from copenet.core.market.intraday.intervals import (
    GRAINS, GRAIN_BY_KEY, INTERVALS, interval_seconds, offerable_intervals, resolve,
)
from copenet.core.market.intraday.resample import bucket_start, resample_intraday, session_anchor
from copenet.core.market.intraday.store import (
    ALL_SESSIONS, EXTENDED, REGULAR, IntradayHistory, IntradayStore, bar_session, filter_session, merge_bars,
)
from copenet.core.market.models import MarketBar

ET = ZoneInfo("America/New_York")
SESSION = datetime(2026, 9, 9)  # a Wednesday


def at(hour: int, minute: int, *, day: int = 9) -> int:
    return int(datetime(2026, 9, day, hour, minute, tzinfo=ET).timestamp())


def bar(hour: int, minute: int, *, day: int = 9, close: float = 10.0, volume: int = 100) -> MarketBar:
    return MarketBar(t=at(hour, minute, day=day), o=close, h=close, l=close, c=close, v=volume)


def et(timestamp: int) -> str:
    return datetime.fromtimestamp(timestamp, tz=ET).strftime("%m-%d %H:%M")


# ------------------------------------------------------------------ the interval algebra


def test_every_offered_interval_resolves_to_a_grain():
    assert offerable_intervals() == INTERVALS


def test_a_derived_interval_takes_the_coarsest_grain_that_divides_it():
    """Coarser grains reach further back, and the candles are identical either way — so
    building 15m from 1m would halve the available history for no gain."""
    assert resolve("15m").grain.key == "5m"
    assert resolve("15m").window_days == 60
    assert resolve("3m").grain.key == "1m"
    assert resolve("4h").grain.key == "1h"


def test_a_native_interval_is_not_marked_derived():
    for key in ("1m", "5m", "1h"):
        assert resolve(key).derived is False, key
    for key in ("2m", "15m", "4h"):
        assert resolve(key).derived is True, key


def test_an_interval_no_grain_divides_is_refused_rather_than_rounded():
    with pytest.raises(ValueError):
        interval_seconds("7m")


def test_only_the_one_minute_grain_is_paged():
    """Measured: 1m serves 30 days but caps a request at 7. Nothing else is capped below
    its window, so 'load earlier' is a 1m affordance and not a general mechanism."""
    paged = [grain.key for grain in GRAINS if grain.paged]

    assert paged == ["1m"]


def test_request_windows_cover_the_span_newest_first():
    windows = _windows(GRAIN_BY_KEY["1m"], 30, SESSION.date())

    assert len(windows) == 5
    # Newest first: an interrupted paged fetch should leave recent history, not a gap.
    assert windows[0][1] > windows[-1][1]
    # Contiguous, no overlap and no hole.
    for newer, older in zip(windows, windows[1:]):
        assert older[1] == newer[0]


def test_an_unpaged_grain_asks_once():
    assert len(_windows(GRAIN_BY_KEY["5m"], 60, SESSION.date())) == 1
    assert len(_windows(GRAIN_BY_KEY["1h"], 730, SESSION.date())) == 1


def test_a_request_cannot_exceed_the_vendor_window():
    windows = _windows(GRAIN_BY_KEY["5m"], 400, SESSION.date())
    span = windows[0][1] - windows[-1][0]

    assert span <= timedelta(days=GRAIN_BY_KEY["5m"].window_days + 1)


# --------------------------------------------------------------------- session anchoring


def test_buckets_anchor_to_the_regular_open_matching_the_vendor():
    """Yahoo's hourly bars run 09:30, 10:30 … 15:30. Derived bars land on the same
    boundaries so fetched and derived candles are interchangeable."""
    assert et(bucket_start(at(9, 30), 3600)) == "09-09 09:30"
    assert et(bucket_start(at(10, 29), 3600)) == "09-09 09:30"
    assert et(bucket_start(at(10, 30), 3600)) == "09-09 10:30"
    # The last regular hourly is a 30-minute stub, exactly as the vendor reports it.
    assert et(bucket_start(at(15, 55), 3600)) == "09-09 15:30"


def test_premarket_buckets_floor_backward_instead_of_folding_into_the_open():
    """Floor division toward negative infinity is load-bearing: truncating toward zero would
    collapse the entire premarket into the 09:30 candle."""
    assert et(bucket_start(at(9, 29), 3600)) == "09-09 08:30"
    assert et(bucket_start(at(8, 45), 3600)) == "09-09 08:30"
    assert et(bucket_start(at(4, 0), 3600)) == "09-09 03:30"


def test_turning_extended_hours_on_does_not_move_a_regular_session_candle():
    """THE invariant that chose the anchor. Anchoring to the extended open instead would
    re-cut every regular-hours candle when the operator toggled the session mode."""
    regular = [bar(9, 30), bar(9, 45), bar(10, 0)]
    with_premarket = [bar(4, 0), bar(7, 30), *regular]

    only_regular = {row.t: row for row in resample_intraday(regular, 1800)}
    including_premarket = {row.t: row for row in resample_intraday(with_premarket, 1800)}

    for timestamp, candle in only_regular.items():
        assert including_premarket[timestamp] == candle, f"{et(timestamp)} moved"


def test_a_bucket_never_spans_two_sessions():
    bars = [bar(19, 0, day=9), bar(4, 0, day=10)]

    rolled = resample_intraday(bars, 4 * 3600)

    assert len(rolled) == 2


# ------------------------------------------------------------------------- the roll-up


def test_the_roll_up_takes_first_open_last_close_and_the_extremes():
    bars = [
        MarketBar(t=at(9, 30), o=10, h=12, l=9, c=11, v=100),
        MarketBar(t=at(9, 35), o=11, h=15, l=10, c=14, v=200),
        MarketBar(t=at(9, 40), o=14, h=14, l=8, c=13, v=300),
    ]

    rolled = resample_intraday(bars, 900)

    assert len(rolled) == 1
    assert (rolled[0].o, rolled[0].h, rolled[0].l, rolled[0].c, rolled[0].v) == (10, 15, 8, 13, 600)


def test_an_overnight_bucket_sums_to_zero_volume_rather_than_going_missing():
    """Overnight volume is structurally absent — measured at 228 of 228 extended 5m bars.
    Zero is the measurement, and a volume-weighted calculation correctly ignores it."""
    # 01:30 and 02:30 are hourly boundaries here, because buckets anchor to :30 — so these
    # two land in the same bucket and 02:30 would not.
    rolled = resample_intraday([bar(2, 0, volume=0), bar(2, 15, volume=0)], 3600)

    assert len(rolled) == 1
    assert et(rolled[0].t) == "09-09 01:30"
    assert rolled[0].v == 0


def test_resampling_is_order_independent():
    ordered = [bar(9, 30), bar(9, 35), bar(9, 40)]

    assert resample_intraday(list(reversed(ordered)), 900) == resample_intraday(ordered, 900)


def test_an_empty_series_resamples_to_empty_and_a_bad_step_raises():
    assert resample_intraday([], 900) == []
    with pytest.raises(ValueError):
        resample_intraday([bar(9, 30)], 0)


# ------------------------------------------------------------------------ session split


def test_session_is_derived_from_the_timestamp_not_stored_beside_it():
    assert bar_session(at(9, 30)) == REGULAR
    assert bar_session(at(15, 59)) == REGULAR
    # 16:00 is the close: the bar stamped at the close belongs to after-hours.
    assert bar_session(at(16, 0)) == EXTENDED
    assert bar_session(at(9, 29)) == EXTENDED
    assert bar_session(at(4, 0)) == EXTENDED


def test_filtering_by_session_keeps_the_superset_intact():
    bars = [bar(4, 0), bar(9, 30), bar(12, 0), bar(18, 0)]

    assert len(filter_session(bars, ALL_SESSIONS)) == 4
    assert len(filter_session(bars, REGULAR)) == 2
    assert len(filter_session(bars, EXTENDED)) == 2
    with pytest.raises(ValueError):
        filter_session(bars, "overnight")


# ------------------------------------------------------------------------- the store


def test_a_revised_bar_replaces_the_stored_one(tmp_path):
    """The vendor rewrites recent bars. Blind append would leave the cache disagreeing with
    the vendor about the most recent session — the one an operator is most likely reading."""
    first = [MarketBar(t=at(15, 55), o=10, h=10, l=10, c=10, v=100)]
    revised = [MarketBar(t=at(15, 55), o=10, h=11, l=9, c=10.5, v=450)]

    merged = merge_bars(first, revised)

    assert len(merged) == 1
    assert merged[0].v == 450
    assert merged[0].c == 10.5


def test_the_store_round_trips_and_merges(tmp_path):
    store = IntradayStore(tmp_path / "intraday")
    store.merge("aapl", "5m", [bar(9, 30), bar(9, 35)], split_fingerprint="fp1")

    store.merge("AAPL", "5m", [bar(9, 35, close=99.0), bar(9, 40)], split_fingerprint="fp1")
    history = store.load("AAPL", "5m")

    assert [et(row.t) for row in history.bars] == ["09-09 09:30", "09-09 09:35", "09-09 09:40"]
    assert history.bars[1].c == 99.0, "the newer fetch should win on collision"
    assert history.symbol == "AAPL"


def test_a_split_rebuilds_the_symbol_instead_of_appending_to_a_stale_basis(tmp_path):
    """A split rewrites the vendor's own history, so every stored bar is on a stale basis.
    Dividends never invalidate; splits always do — the daily cache's rule, same reason."""
    store = IntradayStore(tmp_path / "intraday")
    store.merge("AAPL", "5m", [bar(9, 30), bar(9, 35)], split_fingerprint="before")

    after = store.merge("AAPL", "5m", [bar(10, 0)], split_fingerprint="after")

    assert [et(row.t) for row in after.bars] == ["09-09 10:00"]
    assert after.split_fingerprint == "after"


def test_a_cache_from_another_vendor_or_basis_reads_as_absent(tmp_path):
    from copenet.core._json_store import write_json_atomic

    store = IntradayStore(tmp_path / "intraday")
    path = store.path_for("AAPL", "5m")
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json_atomic(path, {"version": 1, "vendor": "someone-else", "basis": "split_adjusted", "bars": []})

    assert store.load("AAPL", "5m") is None


def test_bars_reload_sorted_regardless_of_write_order(tmp_path):
    store = IntradayStore(tmp_path / "intraday")
    store.save(IntradayHistory(symbol="AAPL", grain="5m", bars=[bar(10, 0), bar(9, 30)]))

    assert [et(row.t) for row in store.load("AAPL", "5m").bars] == ["09-09 09:30", "09-09 10:00"]


def test_dropping_a_symbol_is_idempotent(tmp_path):
    store = IntradayStore(tmp_path / "intraday")
    store.merge("AAPL", "5m", [bar(9, 30)], split_fingerprint="fp")

    assert store.drop("AAPL", "5m") is True
    assert store.drop("AAPL", "5m") is False
    assert store.load("AAPL", "5m") is None


# ------------------------------------------------------------------------- the service

from copenet.core.market.intraday.fetch import FetchResult
from copenet.core.market.intraday.service import IntradayService


class RecordingFetcher:
    """Stands in for the vendor. Records every call so a test can assert on what was NOT
    requested, which is most of what this service exists to control."""

    def __init__(self, bars=None, unavailable=None):
        self.bars = bars if bars is not None else [bar(9, 30), bar(9, 35), bar(9, 40)]
        self.unavailable = unavailable
        self.calls: list[tuple[str, str, int | None]] = []

    def __call__(self, symbol, grain, *, days=None):
        self.calls.append((symbol, grain.key, days))
        if self.unavailable:
            return FetchResult(bars=[], unavailable=self.unavailable)
        return FetchResult(bars=list(self.bars), requests=1)


def service(tmp_path, fetcher, *, splits=()):
    return IntradayService(
        IntradayStore(tmp_path / "intraday"),
        splits_for=lambda symbol: list(splits),
        fetcher=fetcher,
    )


NOW = datetime(2026, 9, 9, 20, 0, tzinfo=ET)


def test_a_fresh_cache_is_served_without_calling_the_vendor(tmp_path):
    fetcher = RecordingFetcher()
    svc = service(tmp_path, fetcher)

    svc.series("AAPL", "5m", now=NOW)
    svc.series("AAPL", "5m", now=NOW)

    assert len(fetcher.calls) == 1, "the second read should hit the cache"


def test_a_derived_interval_reuses_the_grain_already_cached(tmp_path):
    """The payoff of fetching grains rather than intervals: 30m costs nothing once 5m is
    cached, because they are the same stored bars rolled up differently."""
    fetcher = RecordingFetcher()
    svc = service(tmp_path, fetcher)

    svc.series("AAPL", "5m", now=NOW)
    svc.series("AAPL", "15m", now=NOW)
    svc.series("AAPL", "30m", now=NOW)

    assert len(fetcher.calls) == 1
    assert fetcher.calls[0][1] == "5m"


def test_a_stale_cache_is_refreshed(tmp_path):
    fetcher = RecordingFetcher()
    svc = service(tmp_path, fetcher)

    svc.series("AAPL", "5m", now=NOW)
    svc.series("AAPL", "5m", now=NOW + timedelta(hours=2))

    assert len(fetcher.calls) == 2


def test_a_split_rebuilds_the_cache_however_fresh_it_is(tmp_path):
    """A split rewrites the vendor's own history, so recency is irrelevant — every stored
    bar is on a basis that no longer exists."""
    fetcher = RecordingFetcher()
    store = IntradayStore(tmp_path / "intraday")
    before = IntradayService(store, splits_for=lambda s: [], fetcher=fetcher)
    before.series("AAPL", "5m", now=NOW)

    after = IntradayService(store, splits_for=lambda s: [("2026-09-09", 4.0)], fetcher=fetcher)
    after.series("AAPL", "5m", now=NOW)

    assert len(fetcher.calls) == 2


def test_a_refused_grain_with_no_cache_reports_unavailable(tmp_path):
    """`MARKET_SENTINEL_ALERTS.md` rule 5: unsupported data is an explicit state, never an
    empty chart the operator has to interpret."""
    svc = service(tmp_path, RecordingFetcher(unavailable="1m data not available"))

    result = svc.series("AAPL", "1m", now=NOW)

    assert result.bars == []
    assert "not available" in result.unavailable


def test_a_refused_refresh_still_serves_the_cached_bars(tmp_path):
    """Blanking a chart the operator was already reading, because a refresh failed, is worse
    than showing bars that are a few minutes old and saying so."""
    fetcher = RecordingFetcher()
    svc = service(tmp_path, fetcher)
    svc.series("AAPL", "5m", now=NOW)

    fetcher.unavailable = "vendor refused"
    result = svc.series("AAPL", "5m", now=NOW + timedelta(hours=2))

    assert len(result.bars) == 3
    assert result.unavailable is None
    assert any("cached" in warning for warning in result.warnings)


def test_a_regular_session_bucket_never_absorbs_after_hours_trade(tmp_path):
    """Order matters where a bucket spans the close. A 2h bucket anchored at 15:30 runs to
    17:30, so rolling up before filtering would fold after-hours trade into a candle stamped
    15:30 — and the session filter would then KEEP it, because its timestamp is regular. The
    operator asked for regular hours and would be shown a high the session never reached."""
    spanning = [
        MarketBar(t=at(15, 30), o=10, h=10, l=10, c=10, v=100),   # regular
        MarketBar(t=at(16, 30), o=10, h=99, l=10, c=98, v=0),     # after hours, wild print
    ]
    svc = service(tmp_path, RecordingFetcher(bars=spanning))

    regular = svc.series("AAPL", "2h", session=REGULAR, now=NOW)
    everything = svc.series("AAPL", "2h", session=ALL_SESSIONS, now=NOW)

    assert [row.h for row in regular.bars] == [10], "after-hours trade leaked into a regular candle"
    # With every session in scope the same bucket legitimately spans the close.
    assert max(row.h for row in everything.bars) == 99


def test_the_series_reports_the_grain_that_served_it(tmp_path):
    """Not an implementation detail to the operator: the grain is WHY 15m reaches 60 days."""
    svc = service(tmp_path, RecordingFetcher())

    result = svc.series("AAPL", "15m", now=NOW)

    assert result.grain == "5m"
    assert result.window_days == 60


def test_asking_for_more_days_refetches_only_a_paged_grain(tmp_path):
    """Every grain but 1m already holds its whole window, so a deeper request for one of
    them would be a round trip that cannot return anything new."""
    fetcher = RecordingFetcher()
    svc = service(tmp_path, fetcher)
    svc.series("AAPL", "5m", now=NOW)

    svc.series("AAPL", "5m", days=60, now=NOW)

    assert len(fetcher.calls) == 1
