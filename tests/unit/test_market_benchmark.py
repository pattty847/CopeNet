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
    assert verdict.pct == "+0.0%"
