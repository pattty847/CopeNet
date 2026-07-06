from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import pandas as pd

from copenet.core.market.signals import _rrg_axes, _zscore, compute_price_signals, compute_rrg_tail


def _weekly_bars(start_price: float, deltas: list[float]) -> pd.DataFrame:
    rows = []
    price = start_price
    start = datetime(2025, 1, 3, tzinfo=timezone.utc)
    for index, delta in enumerate(deltas):
        open_price = price
        close = price + delta
        high = max(open_price, close) + 2
        low = min(open_price, close) - 2
        rows.append(
            {
                "date": start + timedelta(days=index * 7),
                "open": open_price,
                "high": high,
                "low": low,
                "close": close,
                "volume": 1_000_000 + index * 10_000,
            }
        )
        price = close
    return pd.DataFrame(rows)


def test_compute_price_signals_reports_trend_pullback_and_thin_history() -> None:
    frame = _weekly_bars(100, [2] * 45 + [-3] * 10 + [1] * 5)

    signals = compute_price_signals(frame, benchmark=_weekly_bars(100, [1] * 60))

    assert signals.trend_direction == "up"
    assert signals.below_ma.startswith("-")
    assert signals.drawdown.startswith("-")
    assert 0 <= signals.confluence <= 4
    assert signals.rsi
    assert signals.thin_history is False


def test_compute_price_signals_gracefully_marks_short_history() -> None:
    signals = compute_price_signals(_weekly_bars(25, [2, -1, -0.5]))

    assert signals.thin_history is True
    assert signals.trend_direction in {"up", "down"}
    assert signals.below_ma == "n/a"
    assert signals.drawdown.startswith("-")


def test_compute_rrg_tail_returns_centered_rotation_points_and_quadrant() -> None:
    asset = _weekly_bars(100, [1] * 20 + [3] * 20)
    benchmark = _weekly_bars(100, [1] * 40)

    sector = compute_rrg_tail("XLK", "Technology", asset, benchmark)

    assert sector.symbol == "XLK"
    assert len(sector.tail) == 10
    assert sector.tail == sector.tails["default"]
    assert set(sector.tails) == {"fast", "default", "slow"}
    assert len(sector.tails["fast"]) == 6
    assert len(sector.tails["default"]) == 10
    assert len(sector.tails["slow"]) == 12
    assert sector.quadrant in {"leading", "weakening", "lagging", "improving"}
    assert all(set(point.keys()) == {"x", "y"} for point in sector.tail)
    assert sector.tail[-1]["x"] > 0


def test_rrg_axes_use_smoothed_log_relative_strength_for_level_and_momentum() -> None:
    rs = pd.Series([1.0, 1.01, 1.03, 1.02, 1.06, 1.08, 1.07, 1.1, 1.13, 1.12, 1.16, 1.19])

    x, y = _rrg_axes(rs, window=8, mom_period=2, smooth=2)

    smoothed = rs.map(math.log).ewm(span=2, adjust=False, min_periods=1).mean()
    expected_x = _zscore(smoothed, window=8, min_periods=4)
    expected_y = _zscore(smoothed.diff(2), window=8, min_periods=4)
    pd.testing.assert_series_equal(x, expected_x)
    pd.testing.assert_series_equal(y, expected_y)
