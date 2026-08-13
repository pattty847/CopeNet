"""Leakage-safe expanding-window model evaluation."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

import numpy as np
import pandas as pd

from .evaluate import ranking_metrics, regression_metrics, strategy_metrics
from .features import FEATURE_SETS
from .models import MODEL_NAMES, build_model, feature_contribution


def walk_forward(
    dataset: pd.DataFrame,
    *,
    minimum_training_rows: int,
    seed: int,
    cost_bps: float,
) -> tuple[pd.DataFrame, dict[str, Any], dict[str, Any]]:
    predictions: list[dict[str, Any]] = []
    contributions: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    dataset = dataset.copy()
    dataset["prediction_time_utc"] = pd.to_datetime(dataset["prediction_timestamp"], utc=True)
    dataset["target_reveal_time_utc"] = pd.to_datetime(dataset["target_end_12m"], utc=True)
    periods = sorted(dataset["prediction_time_utc"].unique())
    for feature_set_name, feature_names in FEATURE_SETS.items():
        for model_name in MODEL_NAMES:
            for period in periods:
                train = dataset[
                    (dataset["prediction_time_utc"] < period)
                    & (dataset["target_reveal_time_utc"] < period)
                ]
                test = dataset[dataset["prediction_time_utc"] == period]
                if len(train) < minimum_training_rows or test.empty:
                    continue
                model = build_model(model_name, seed)
                model.fit(train[list(feature_names)], train["excess_return_12m"])
                predicted = model.predict(test[list(feature_names)])
                contributions[feature_set_name][model_name].append({
                    "prediction_timestamp": str(period),
                    "training_rows": len(train),
                    "values": feature_contribution(model, feature_names),
                })
                for (_, row), value in zip(test.iterrows(), predicted):
                    predictions.append({
                        **row.drop(labels=["prediction_time_utc", "target_reveal_time_utc"]).to_dict(),
                        "feature_set": feature_set_name,
                        "model": model_name,
                        "predicted": float(value),
                        "training_rows": len(train),
                    })
    frame = pd.DataFrame(predictions)
    summary: dict[str, Any] = {}
    for (feature_set, model_name), group in frame.groupby(["feature_set", "model"]):
        key = f"{feature_set}:{model_name}"
        rankable = model_name != "naive"
        summary[key] = {
            **regression_metrics(group["excess_return_12m"], group["predicted"]),
            "ranking": ranking_metrics(group.rename(columns={"excess_return_12m": "actual"})) if rankable else {},
            "top_1_strategy": strategy_metrics(group, top_n=1, cost_bps=cost_bps) if rankable else {},
            "top_2_strategy": strategy_metrics(group, top_n=2, cost_bps=cost_bps) if rankable else {},
            "rankable": rankable,
            "predictions": len(group),
        }
    return frame, summary, contributions
