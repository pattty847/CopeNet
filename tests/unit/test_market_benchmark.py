from __future__ import annotations

import pandas as pd

from copenet.core.market.benchmark import benchmark_verdict


def _weekly_frame(closes: list[float]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.date_range("2020-01-03", periods=len(closes), freq="W-FRI"),
            "close": closes,
        }
    )


def test_benchmark_verdict_uses_trailing_52_weeks_not_lifetime_starting_price() -> None:
    recent = [100.0 + index for index in range(53)]
    asset = _weekly_frame([1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 64.0] + recent)
    benchmark = _weekly_frame([100.0] * 7 + recent)

    verdict = benchmark_verdict(asset, {"VOO": benchmark})[0]

    assert verdict.label == "In line"
    assert verdict.excess_return_pct == 0.0
    assert verdict.beta_adjusted_excess_pct == 0.0


def test_benchmark_verdict_headline_uses_actual_relative_performance() -> None:
    benchmark = _weekly_frame([100.0 + index for index in range(53)])
    asset = _weekly_frame([100.0 + (index * 2.0) for index in range(53)])

    verdict = benchmark_verdict(asset, {"VOO": benchmark})[0]

    assert verdict.label == "Beats"
    assert verdict.excess_return_pct is not None and verdict.excess_return_pct > 10
    assert verdict.asset_return_pct is not None
    assert verdict.benchmark_return_pct is not None
    assert verdict.beta is not None
