"""Out-of-sample regression, ranking, and strategy diagnostics."""

from __future__ import annotations

import math
from typing import Any
from collections import Counter

import numpy as np
import pandas as pd
from scipy.stats import pearsonr, spearmanr


def regression_metrics(actual: pd.Series, predicted: pd.Series) -> dict[str, float]:
    errors = predicted - actual
    variance = float(((actual - actual.mean()) ** 2).sum())
    r2 = 1.0 - float((errors**2).sum()) / variance if variance > 0 else 0.0
    pearson = float(pearsonr(actual, predicted).statistic) if len(actual) > 1 and actual.nunique() > 1 and predicted.nunique() > 1 else 0.0
    spearman = float(spearmanr(actual, predicted).statistic) if len(actual) > 1 and actual.nunique() > 1 and predicted.nunique() > 1 else 0.0
    return {
        "mae": float(errors.abs().mean()),
        "rmse": float(np.sqrt((errors**2).mean())),
        "r2": r2,
        "directional_accuracy": float(((actual >= 0) == (predicted >= 0)).mean()),
        "spearman": spearman if math.isfinite(spearman) else 0.0,
        "pearson": pearson if math.isfinite(pearson) else 0.0,
    }


def ranking_metrics(predictions: pd.DataFrame) -> dict[str, float]:
    periods: list[dict[str, float]] = []
    for _, group in predictions.groupby("prediction_timestamp"):
        ranked = group.sort_values(["predicted", "ticker"], ascending=[False, True])
        periods.append({
            "top_1_actual_excess": float(ranked.iloc[0]["actual"]),
            "top_2_actual_excess": float(ranked.iloc[:2]["actual"].mean()),
            "bottom_1_actual_excess": float(ranked.iloc[-1]["actual"]),
            "rank_correlation": float(spearmanr(ranked["predicted"], ranked["actual"]).statistic) if ranked["predicted"].nunique() > 1 and ranked["actual"].nunique() > 1 else 0.0,
            "top_1_hit": float(ranked.iloc[0]["actual"] > 0),
            "top_2_hit": float(ranked.iloc[:2]["actual"].mean() > 0),
        })
    frame = pd.DataFrame(periods)
    return {key: float(frame[key].mean()) for key in frame.columns} if not frame.empty else {}


def max_drawdown(nav: list[float]) -> float:
    values = np.asarray(nav, dtype=float)
    peaks = np.maximum.accumulate(values)
    return float(np.min(values / peaks - 1.0)) if len(values) else 0.0


def strategy_metrics(predictions: pd.DataFrame, *, top_n: int, cost_bps: float) -> dict[str, Any]:
    nav = 1.0
    benchmark_nav = 1.0
    old_weights: dict[str, float] = {}
    nav_path = [nav]
    turnover_total = 0.0
    periods = 0
    first_start: pd.Timestamp | None = None
    last_end: pd.Timestamp | None = None
    selections: Counter[str] = Counter()
    for _, group in predictions.groupby("prediction_timestamp", sort=True):
        if group["holding_period_return"].isna().any() or group["benchmark_holding_period_return"].isna().any():
            continue
        ranked = group.sort_values(["predicted", "ticker"], ascending=[False, True]).head(top_n)
        new_weights = {ticker: 1.0 / len(ranked) for ticker in ranked["ticker"]}
        selections.update(str(ticker) for ticker in ranked["ticker"])
        turnover = sum(abs(new_weights.get(ticker, 0.0) - old_weights.get(ticker, 0.0)) for ticker in set(old_weights) | set(new_weights))
        cost = turnover * cost_bps / 10_000.0
        period_return = float(ranked["holding_period_return"].mean())
        benchmark_return = float(group["benchmark_holding_period_return"].iloc[0])
        nav *= max(0.0, 1.0 - cost) * (1.0 + period_return)
        benchmark_nav *= 1.0 + benchmark_return
        nav_path.append(nav)
        turnover_total += turnover
        periods += 1
        first_start = pd.to_datetime(group["prediction_timestamp"].iloc[0], utc=True) if first_start is None else first_start
        last_end = pd.to_datetime(group["holding_period_end"].iloc[0], utc=True)
        old_weights = new_weights
    years = (last_end - first_start).days / 365.2425 if first_start is not None and last_end is not None else 0.0
    return {
        "cumulative_return": nav - 1.0,
        "cagr": nav ** (1.0 / years) - 1.0 if years > 0 and nav > 0 else 0.0,
        "benchmark_cagr": benchmark_nav ** (1.0 / years) - 1.0 if years > 0 else 0.0,
        "max_drawdown": max_drawdown(nav_path),
        "average_gross_traded_notional": turnover_total / periods if periods else 0.0,
        "average_one_way_turnover": turnover_total / (2 * periods) if periods else 0.0,
        "transaction_cost_bps": cost_bps,
        "periods": float(periods),
        "selection_counts": dict(sorted(selections.items())),
        "largest_selection_share": max(selections.values()) / sum(selections.values()) if selections else 0.0,
    }


def static_strategy_controls(dataset: pd.DataFrame, *, start_timestamp: str, cost_bps: float) -> dict[str, Any]:
    eligible = dataset[
        (pd.to_datetime(dataset["prediction_timestamp"], utc=True) >= pd.to_datetime(start_timestamp, utc=True))
        & dataset["holding_period_return"].notna()
    ]
    controls: dict[str, Any] = {}
    grouped = eligible.groupby("prediction_timestamp", sort=True)
    for symbol in sorted(eligible["ticker"].unique()):
        rows = eligible[eligible["ticker"] == symbol].sort_values("prediction_timestamp")
        if rows.empty:
            continue
        nav = (1.0 - cost_bps / 10_000.0) * float((1.0 + rows["holding_period_return"]).prod())
        years = (pd.to_datetime(rows["holding_period_end"].iloc[-1], utc=True) - pd.to_datetime(rows["prediction_timestamp"].iloc[0], utc=True)).days / 365.2425
        controls[symbol] = {"cagr": nav ** (1.0 / years) - 1.0, "periods": len(rows)}
    period_returns = grouped["holding_period_return"].mean()
    if not period_returns.empty:
        nav = (1.0 - cost_bps / 10_000.0) * float((1.0 + period_returns).prod())
        first = pd.to_datetime(eligible["prediction_timestamp"], utc=True).min()
        last = pd.to_datetime(eligible["holding_period_end"].dropna(), utc=True).max()
        years = (last - first).days / 365.2425
        controls["equal_weight_five"] = {"cagr": nav ** (1.0 / years) - 1.0, "periods": len(period_returns)}
    return controls
