"""Unit tests for the Insight Engine feature library (pure, point-in-time)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from copenet.core.market.features import FEATURE_CATALOG_VERSION, compute_features


def _frame(closes: list[float], *, volumes: list[float] | None = None) -> pd.DataFrame:
    n = len(closes)
    dates = pd.date_range("2020-01-06", periods=n, freq="W-MON")
    closes_arr = np.array(closes, dtype=float)
    vols = volumes if volumes is not None else [1_000_000.0] * n
    return pd.DataFrame(
        {
            "date": dates,
            "open": closes_arr,
            "high": closes_arr * 1.01,
            "low": closes_arr * 0.99,
            "close": closes_arr,
            "volume": vols,
        }
    )


def test_empty_frame_is_safe():
    fs = compute_features(pd.DataFrame(), symbol="X")
    assert fs.history_weeks == 0
    assert fs.thin_history is True
    assert fs.soft_bottoming is False
    assert fs.r_4w is None
    assert fs.ma_stack == "n/a"


def test_catalog_version_pinned():
    # base rates are keyed by this — changing feature math must bump it deliberately
    assert FEATURE_CATALOG_VERSION == "v1"


def test_uptrend_features_are_sane():
    closes = list(np.linspace(100, 200, 60))  # steady uptrend
    fs = compute_features(_frame(closes), symbol="UP")
    assert fs.history_weeks == 60
    assert fs.thin_history is False
    assert fs.r_4w is not None and fs.r_4w > 0
    assert fs.r_52w is not None and fs.r_52w > 0
    assert fs.ma_stack == "above"
    assert fs.drawdown_pct is not None and fs.drawdown_pct == 0.0  # at the highs
    assert fs.soft_bottoming is False  # an uptrend is not a bottom


def test_soft_bottoming_fires_on_a_bottoming_shape():
    # decline into a low, hold a higher low, curl up and reclaim the short MA
    decline = list(np.linspace(100, 50, 30))
    base = [50, 49, 51, 50, 52, 51, 54, 53, 56, 58]  # higher lows + recovery
    recovery = list(np.linspace(58, 66, 12))
    fs = compute_features(_frame(decline + base + recovery), symbol="BOT")
    assert fs.drawdown_pct is not None and fs.drawdown_pct < -10
    assert fs.sb_lower_lows_stopped is True
    assert fs.sb_higher_low is True
    assert fs.soft_bottoming_score >= 0.5


def test_no_lookahead_slice_independence():
    """A feature computed as-of bar k must not change when future bars are appended.

    This is the structural lookahead guard: compute_features only sees the frame it is given,
    so slicing to `as_of` makes future data unreachable.
    """
    closes = list(100 + 30 * np.sin(np.linspace(0, 8, 120)))
    full = _frame(closes)
    k = 70
    as_of = compute_features(full.iloc[:k].copy(), symbol="A")
    # append wildly different future bars; the as-of view must be byte-identical
    appended = full.copy()
    appended.loc[k:, "close"] = 999.0
    as_of_again = compute_features(appended.iloc[:k].copy(), symbol="A")
    assert as_of.to_dict() == as_of_again.to_dict()
