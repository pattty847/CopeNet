"""5-state trend classifier: state calls on synthetic regimes, chop resistance, point-in-time safety."""

from __future__ import annotations

import math

import pandas as pd
import pytest

from copenet.core.market.trend_states import (
    MIN_HISTORY_WEEKS,
    TrendState,
    classify_trend,
    classify_trend_series,
)


def _frame(closes: list[float], spread: float = 0.01) -> pd.DataFrame:
    dates = pd.date_range("2018-01-05", periods=len(closes), freq="W-FRI")
    return pd.DataFrame(
        {
            "date": dates,
            "open": closes,
            "high": [c * (1 + spread) for c in closes],
            "low": [c * (1 - spread) for c in closes],
            "close": closes,
            "volume": [1_000_000] * len(closes),
        }
    )


def _wiggle(i: int, scale: float) -> float:
    # deterministic pseudo-noise so tests never depend on a RNG seed
    return scale * math.sin(i * 1.7) * 0.5


def test_clean_uptrend_is_strong_up() -> None:
    closes = [100 * (1.008**i) * (1 + _wiggle(i, 0.01)) for i in range(120)]
    snap = classify_trend(_frame(closes), symbol="TEST")
    assert snap.state == TrendState.STRONG_UP.value
    assert snap.thin_history is False
    assert snap.weeks_in_state >= 2
    assert snap.slope40_atr is not None and snap.slope40_atr > 0


def test_clean_downtrend_is_strong_down() -> None:
    closes = [100 * (0.992**i) * (1 + _wiggle(i, 0.01)) for i in range(120)]
    snap = classify_trend(_frame(closes), symbol="TEST")
    assert snap.state == TrendState.STRONG_DOWN.value
    assert snap.slope40_atr is not None and snap.slope40_atr < 0


def test_flat_chop_is_transition_and_never_flips_up_down() -> None:
    closes = [100 * (1 + _wiggle(i, 0.06)) for i in range(150)]
    series = classify_trend_series(_frame(closes))
    assert not series.empty
    # a flat, noisy tape should live mostly in TRANSITION...
    share = (series["state"] == TrendState.TRANSITION.value).mean()
    assert share > 0.5
    # ...and must never jump directly between UP-family and DOWN-family states
    ups = {TrendState.UP.value, TrendState.STRONG_UP.value}
    downs = {TrendState.DOWN.value, TrendState.STRONG_DOWN.value}
    pairs = zip(series["state"], series["state"].iloc[1:], strict=False)
    direct_flips = sum(1 for a, b in pairs if (a in ups and b in downs) or (a in downs and b in ups))
    assert direct_flips == 0


def test_price_above_falling_ma40_is_not_up() -> None:
    """The old-rule bug case: a rally above a still-falling 40-week average is TRANSITION."""
    # long decline, then a sharp 6-week bounce that clears MA40 while its slope is still negative
    closes = [200 * (0.985**i) for i in range(100)]
    bounce_start = closes[-1]
    closes += [bounce_start * (1.05**i) for i in range(1, 7)]
    series = classify_trend_series(_frame(closes))
    last = series.iloc[-1]
    assert last["dist40_atr"] > 0  # price genuinely above the anchor
    assert last["slope40_atr"] < 0  # anchor still falling
    assert last["state"] in (TrendState.TRANSITION.value, TrendState.DOWN.value)
    assert last["state"] != TrendState.UP.value


def test_strong_entry_requires_persistence() -> None:
    """The first week the full-stack condition appears must not print STRONG yet."""
    closes = [100 * (1.008**i) * (1 + _wiggle(i, 0.01)) for i in range(120)]
    series = classify_trend_series(_frame(closes))
    states = series["state"].tolist()
    first_strong = states.index(TrendState.STRONG_UP.value)
    assert first_strong > 0
    assert states[first_strong - 1] != TrendState.STRONG_DOWN.value  # sanity
    # the bar before the first STRONG_UP must be a non-strong state (the gate held one week)
    assert states[first_strong - 1] in (TrendState.UP.value, TrendState.TRANSITION.value)


def test_thin_history_returns_unclassified() -> None:
    closes = [100.0 + i for i in range(MIN_HISTORY_WEEKS - 1)]
    snap = classify_trend(_frame(closes), symbol="THIN")
    assert snap.state is None
    assert snap.thin_history is True
    assert classify_trend_series(_frame(closes)).empty


def test_slice_independence() -> None:
    """State at bar t is identical computed live (slice to t) or in a full-series replay."""
    closes = [100 * (1.004**i) * (1 + _wiggle(i, 0.04)) for i in range(160)]
    # bend the tape: decline in the middle, recovery at the end
    closes = closes[:60] + [closes[59] * (0.985**i) for i in range(1, 51)] + [
        closes[59] * (0.985**50) * (1.01**i) for i in range(1, 51)
    ]
    frame = _frame(closes)
    full = classify_trend_series(frame)
    for i in (80, 110, 140, len(closes) - 1):
        sliced = classify_trend(frame.iloc[: i + 1])
        row = full[full["date"] == frame["date"].iloc[i]]
        assert not row.empty, f"bar {i} missing from full series"
        assert sliced.state == row["state"].iloc[0], f"slice mismatch at bar {i}"


def test_snapshot_dwell_and_prior_state() -> None:
    closes = [100 * (0.99**i) for i in range(80)] + [
        100 * (0.99**79) * (1.012**i) for i in range(1, 61)
    ]
    snap = classify_trend(_frame(closes), symbol="TEST", as_of="2025-01-01")
    assert snap.state in (TrendState.UP.value, TrendState.STRONG_UP.value)
    assert snap.weeks_in_state >= 1
    assert snap.entered_at is not None
    assert snap.prior_state is not None
    assert snap.prior_state != snap.state
    assert snap.as_of == "2025-01-01"


def test_close_only_frame_still_classifies() -> None:
    closes = [100 * (1.008**i) for i in range(120)]
    dates = pd.date_range("2018-01-05", periods=len(closes), freq="W-FRI")
    frame = pd.DataFrame({"date": dates, "close": closes})
    snap = classify_trend(frame)
    assert snap.state == TrendState.STRONG_UP.value


@pytest.mark.parametrize("n", [0, 1, 10])
def test_degenerate_frames(n: int) -> None:
    closes = [100.0] * n
    snap = classify_trend(_frame(closes) if n else pd.DataFrame())
    assert snap.state is None
    assert snap.thin_history is True
