from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd

from copenet.core.market.signals import compute_price_signals, compute_rrg_tail


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

    sector = compute_rrg_tail("XLK", "Technology", asset, benchmark, points=8)

    assert sector.symbol == "XLK"
    assert len(sector.tail) == 8
    assert sector.quadrant in {"leading", "weakening", "lagging", "improving"}
    assert all(set(point.keys()) == {"x", "y"} for point in sector.tail)
    assert sector.tail[-1]["x"] > 0
