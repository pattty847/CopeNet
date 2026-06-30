"""Unit tests for base-rate aggregation (the calibration / honesty layer)."""
from copenet.core.market.base_rates import BaseRate, build_base_rate, load_base_rate, save_base_rate
from copenet.core.market.features import FEATURE_CATALOG_VERSION


def _events():
    return [
        {"as_of": "2021-01-01", "fwd_return": 5.0, "mae": -3.0, "beat_bench": True, "regime": "bull"},
        {"as_of": "2021-02-01", "fwd_return": -4.0, "mae": -9.0, "beat_bench": False, "regime": "bull"},
        {"as_of": "2022-03-01", "fwd_return": 8.0, "mae": -2.0, "beat_bench": True, "regime": "bear"},
        {"as_of": "2022-06-01", "fwd_return": 2.0, "mae": -6.0, "beat_bench": False, "regime": "bear"},
    ]


def test_build_base_rate_aggregates_honestly():
    rate = build_base_rate(_events(), pattern="soft_bottoming", horizon_weeks=8,
                           universe_id="test", generated_at="2026-06-30T00:00:00Z")
    assert rate.n == 4
    assert rate.pct_up == 75.0          # 3 of 4 positive
    assert rate.pct_beat_bench == 50.0  # 2 of 4 beat bench
    assert rate.bear_n == 2 and rate.bear_pct_up == 100.0
    assert rate.feature_catalog_version == FEATURE_CATALOG_VERSION
    assert "n=4" in rate.headline()


def test_empty_events_are_safe():
    rate = build_base_rate([], pattern="soft_bottoming", horizon_weeks=8, universe_id="t", generated_at="x")
    assert rate.n == 0
    assert "too few" in rate.headline()


def test_save_load_roundtrip(tmp_path):
    rate = build_base_rate(_events(), pattern="soft_bottoming", horizon_weeks=8,
                           universe_id="test", generated_at="2026-06-30T00:00:00Z")
    save_base_rate(rate, root=tmp_path)
    loaded = load_base_rate("soft_bottoming", 8, root=tmp_path)
    assert isinstance(loaded, BaseRate)
    assert loaded.n == 4 and loaded.pct_up == 75.0
