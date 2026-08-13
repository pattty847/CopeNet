"""Fixed, deterministic model factories and fold-local preprocessing."""

from __future__ import annotations

from typing import Any

import numpy as np
from sklearn.base import BaseEstimator
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LinearRegression, Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


MODEL_NAMES = ("naive", "ols", "ridge", "random_forest", "gradient_boosting")


class MeanRegressor(BaseEstimator):
    def fit(self, _x: Any, y: Any) -> "MeanRegressor":
        self.mean_ = float(np.mean(y))
        return self

    def predict(self, x: Any) -> np.ndarray:
        return np.full(len(x), self.mean_, dtype=float)


def build_model(name: str, seed: int) -> Any:
    if name == "naive":
        return Pipeline([("imputer", SimpleImputer(strategy="median", keep_empty_features=True)), ("model", MeanRegressor())])
    if name == "ols":
        return Pipeline([
            ("imputer", SimpleImputer(strategy="median", keep_empty_features=True)),
            ("scaler", StandardScaler()),
            ("model", LinearRegression()),
        ])
    if name == "ridge":
        return Pipeline([
            ("imputer", SimpleImputer(strategy="median", keep_empty_features=True)),
            ("scaler", StandardScaler()),
            ("model", Ridge(alpha=10.0)),
        ])
    if name == "random_forest":
        return Pipeline([
            ("imputer", SimpleImputer(strategy="median", keep_empty_features=True)),
            ("model", RandomForestRegressor(n_estimators=300, max_depth=4, min_samples_leaf=3, random_state=seed, n_jobs=1)),
        ])
    if name == "gradient_boosting":
        return Pipeline([
            ("imputer", SimpleImputer(strategy="median", keep_empty_features=True)),
            ("model", GradientBoostingRegressor(n_estimators=120, learning_rate=0.03, max_depth=2, min_samples_leaf=3, random_state=seed, loss="huber")),
        ])
    raise ValueError(f"unknown model: {name}")


def feature_contribution(model: Pipeline, feature_names: tuple[str, ...]) -> dict[str, float]:
    estimator = model.named_steps["model"]
    values = getattr(estimator, "coef_", None)
    if values is None:
        values = getattr(estimator, "feature_importances_", None)
    if values is None:
        return {}
    return {name: float(value) for name, value in zip(feature_names, np.asarray(values).ravel())}
