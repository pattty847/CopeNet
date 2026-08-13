"""Price-derived features and forward total-return labels."""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd


def price_on_or_after(series: pd.Series, day: date) -> tuple[pd.Timestamp, float] | None:
    eligible = series[series.index.date >= day]
    if eligible.empty:
        return None
    return eligible.index[0], float(eligible.iloc[0])


def price_before(series: pd.Series, day: date) -> tuple[pd.Timestamp, float] | None:
    eligible = series[series.index.date < day]
    if eligible.empty:
        return None
    return eligible.index[-1], float(eligible.iloc[-1])


def total_return(series: pd.Series, start: date, months: int) -> tuple[float, str] | None:
    entry = price_on_or_after(series, start)
    exit_day = (pd.Timestamp(start) + pd.DateOffset(months=months)).date()
    exit_price = price_on_or_after(series, exit_day)
    if entry is None or exit_price is None:
        return None
    return exit_price[1] / entry[1] - 1.0, exit_price[0].date().isoformat()


def forward_targets(stock: pd.Series, benchmark: pd.Series, start: date) -> dict[str, float | str] | None:
    output: dict[str, float | str] = {}
    for months in (6, 12, 24):
        stock_result = total_return(stock, start, months)
        benchmark_result = total_return(benchmark, start, months)
        if stock_result is None or benchmark_result is None:
            if months == 12:
                return None
            continue
        output[f"forward_return_{months}m"] = stock_result[0]
        output[f"benchmark_forward_return_{months}m"] = benchmark_result[0]
        output[f"excess_return_{months}m"] = stock_result[0] - benchmark_result[0]
        output[f"target_end_{months}m"] = max(stock_result[1], benchmark_result[1])
    return output


def market_features(split_adjusted: pd.Series, cutoff: date) -> dict[str, float | None]:
    history = split_adjusted[split_adjusted.index.date < cutoff]
    if history.empty:
        return {"momentum_6m": None, "momentum_12m": None, "volatility_12m": None}
    last = float(history.iloc[-1])

    def momentum(months: int) -> float | None:
        prior_day = (pd.Timestamp(cutoff) - pd.DateOffset(months=months)).date()
        prior = price_on_or_after(history, prior_day)
        return None if prior is None else last / prior[1] - 1.0

    one_year = history[history.index >= pd.Timestamp(cutoff) - pd.DateOffset(months=12)]
    volatility = float(one_year.pct_change().dropna().std() * np.sqrt(252)) if len(one_year) > 2 else None
    return {"momentum_6m": momentum(6), "momentum_12m": momentum(12), "volatility_12m": volatility}
