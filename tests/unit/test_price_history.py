"""Behavioral contracts for daily-price transforms.

These pin the rules that make an append-only price cache safe: dividends are applied on
read (never stored), splits are the only event that invalidates history, and derived
weekly/monthly bars keep Yahoo's anchoring so overlay timestamps stay on candle slots.
"""

from __future__ import annotations

from datetime import date

import pytest

from copenet.core.market.models import MarketBar
from copenet.core.market.price_history import (
    MONTHLY,
    SPLIT_ADJUSTED,
    TOTAL_RETURN,
    WEEKLY,
    apply_dividend_adjustment,
    bar_date,
    derive_bars,
    merge_actions,
    merge_daily_bars,
    resample_bars,
    split_fingerprint,
    utc_midnight,
)


def bar(day: str, *, o: float, h: float, l: float, c: float, v: int = 100) -> MarketBar:
    return MarketBar(t=utc_midnight(date.fromisoformat(day)), o=o, h=h, l=l, c=c, v=v)


def test_weekly_bars_anchor_to_monday_even_when_monday_is_a_holiday() -> None:
    # 2026-01-05 is a Monday; start the week on Tuesday to simulate a holiday.
    week = [
        bar("2026-01-06", o=10, h=12, l=9, c=11, v=1),
        bar("2026-01-07", o=11, h=15, l=8, c=14, v=2),
        bar("2026-01-08", o=14, h=16, l=13, c=13, v=4),
    ]
    weekly = resample_bars(week, WEEKLY)

    assert len(weekly) == 1
    # Anchored to the Monday, not the first trading day. Overlay points snap to candle
    # timestamps; a Tuesday-anchored bar would inject a new slot into the chart's axis.
    assert bar_date(weekly[0]) == date(2026, 1, 5)
    assert (weekly[0].o, weekly[0].h, weekly[0].l, weekly[0].c) == (10, 16, 8, 13)
    assert weekly[0].v == 7


def test_monthly_bars_anchor_to_the_first_of_the_month_and_split_by_month() -> None:
    monthly = resample_bars(
        [
            bar("2026-01-20", o=10, h=11, l=9, c=10),
            bar("2026-01-30", o=10, h=14, l=10, c=13),
            bar("2026-02-03", o=13, h=13, l=7, c=8),
        ],
        MONTHLY,
    )

    assert [bar_date(row) for row in monthly] == [date(2026, 1, 1), date(2026, 2, 1)]
    assert (monthly[0].o, monthly[0].h, monthly[0].l, monthly[0].c) == (10, 14, 9, 13)
    assert (monthly[1].o, monthly[1].h, monthly[1].l, monthly[1].c) == (13, 13, 7, 8)


def test_dividend_adjustment_scales_only_bars_before_the_ex_date() -> None:
    bars = [
        bar("2026-03-02", o=100, h=100, l=100, c=100),
        bar("2026-03-03", o=100, h=100, l=100, c=100),  # ex-date
        bar("2026-03-04", o=100, h=100, l=100, c=100),
    ]

    adjusted = apply_dividend_adjustment(bars, [("2026-03-03", 5.0)])

    # 1 - 5/100 applied to everything strictly before the ex-date.
    assert adjusted[0].c == pytest.approx(95.0)
    # The ex-date bar and everything after it is untouched, which is why the most recent
    # price is identical on both bases and they only diverge looking backwards.
    assert adjusted[1].c == pytest.approx(100.0)
    assert adjusted[2].c == pytest.approx(100.0)


def test_dividend_adjustment_compounds_backwards_across_multiple_payments() -> None:
    bars = [bar(f"2026-03-0{day}", o=100, h=100, l=100, c=100) for day in range(1, 6)]

    adjusted = apply_dividend_adjustment(
        bars,
        [("2026-03-03", 10.0), ("2026-03-05", 10.0)],
    )

    assert adjusted[0].c == pytest.approx(81.0)  # 0.9 * 0.9
    assert adjusted[2].c == pytest.approx(90.0)  # only the later dividend applies
    assert adjusted[4].c == pytest.approx(100.0)


def test_dividend_adjustment_never_scales_volume() -> None:
    bars = [
        bar("2026-03-02", o=100, h=100, l=100, c=100, v=5_000),
        bar("2026-03-03", o=100, h=100, l=100, c=100, v=6_000),
    ]

    adjusted = apply_dividend_adjustment(bars, [("2026-03-03", 50.0)])

    assert [row.v for row in adjusted] == [5_000, 6_000]


def test_stored_basis_is_untouched_by_dividends_and_total_return_is_derived() -> None:
    bars = [
        bar("2026-03-02", o=100, h=100, l=100, c=100),
        bar("2026-03-03", o=100, h=100, l=100, c=100),
    ]
    dividends = [("2026-03-03", 5.0)]

    stored = derive_bars(bars, dividends, basis=SPLIT_ADJUSTED)
    total_return = derive_bars(bars, dividends, basis=TOTAL_RETURN)

    assert [row.c for row in stored] == [100.0, 100.0]
    assert total_return[0].c == pytest.approx(95.0)


def test_split_fingerprint_changes_when_a_split_appears() -> None:
    before = split_fingerprint([("2020-08-31", 4.0)])

    assert before == split_fingerprint([("2020-08-31", 4.0)])
    # A new split means every stored price is on a stale basis and must be rebuilt.
    assert before != split_fingerprint([("2020-08-31", 4.0), ("2024-06-10", 10.0)])


def test_merging_overwrites_the_provisional_current_bar_rather_than_duplicating_it() -> None:
    cached = [bar("2026-03-02", o=10, h=11, l=9, c=10, v=500)]
    # Same day re-fetched later in the session: more volume, a moved close.
    fresher = [bar("2026-03-02", o=10, h=13, l=9, c=12, v=900)]

    merged = merge_daily_bars(cached, fresher)

    assert len(merged) == 1
    assert (merged[0].c, merged[0].v) == (12, 900)


def test_merging_keeps_history_sorted_and_deduplicated() -> None:
    merged = merge_daily_bars(
        [bar("2026-03-03", o=1, h=1, l=1, c=1)],
        [bar("2026-03-01", o=2, h=2, l=2, c=2), bar("2026-03-02", o=3, h=3, l=3, c=3)],
    )

    assert [bar_date(row) for row in merged] == [
        date(2026, 3, 1),
        date(2026, 3, 2),
        date(2026, 3, 3),
    ]


def test_merging_actions_keeps_one_event_per_date() -> None:
    merged = merge_actions([("2026-03-03", 0.25)], [("2026-03-03", 0.26), ("2026-06-03", 0.3)])

    assert merged == [("2026-03-03", 0.26), ("2026-06-03", 0.3)]


def test_unknown_basis_and_timeframe_are_rejected_rather_than_silently_defaulted() -> None:
    with pytest.raises(ValueError):
        derive_bars([], [], basis="adj_close")
    with pytest.raises(ValueError):
        resample_bars([bar("2026-03-02", o=1, h=1, l=1, c=1)], "hourly")
