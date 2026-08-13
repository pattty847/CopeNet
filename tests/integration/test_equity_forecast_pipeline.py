from __future__ import annotations

import pandas as pd

from copenet.core.research_lab.equity_forecast.features import FEATURE_SETS
from copenet.core.research_lab.equity_forecast.walk_forward import walk_forward


def test_historical_features_to_walk_forward_prediction_and_evaluation() -> None:
    rows = []
    periods = pd.date_range("2014-02-17", periods=32, freq="QS-FEB")
    for index, period in enumerate(periods):
        for ticker_index, ticker in enumerate(("AAPL", "MSFT", "AMZN", "GOOGL", "XOM")):
            fundamental = ticker_index * 0.1 + index * 0.002
            row = {
                "ticker": ticker,
                "prediction_timestamp": period.tz_localize("America/New_York").replace(hour=16).isoformat(),
                "target_end_12m": (period + pd.DateOffset(months=12)).tz_localize("America/New_York").replace(hour=16).isoformat(),
                "excess_return_12m": fundamental * 0.2 - 0.03,
                "holding_period_return": fundamental * 0.02,
                "benchmark_holding_period_return": 0.015,
                "holding_period_end": (period + pd.DateOffset(months=3)).isoformat(),
            }
            for feature in {item for values in FEATURE_SETS.values() for item in values}:
                row[feature] = fundamental
            rows.append(row)
    predictions, metrics, importance = walk_forward(pd.DataFrame(rows), minimum_training_rows=20, seed=847, cost_bps=10)
    assert not predictions.empty
    assert "fundamentals_only:ridge" in metrics
    assert metrics["fundamentals_only:ridge"]["predictions"] > 0
    assert importance["fundamentals_only"]["ridge"]
