"""Stable contracts for the baseline equity forecast experiment."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


EXPERIMENT_VERSION = "baseline_equity_forecast_v1.0.1"
DEFAULT_SYMBOLS = ("AAPL", "MSFT", "AMZN", "GOOGL", "NVDA")
HORIZON_MONTHS = (6, 12, 24)


@dataclass(frozen=True)
class ExperimentConfig:
    symbols: tuple[str, ...] = DEFAULT_SYMBOLS
    benchmark: str = "SPY"
    start_year: int = 2014
    end_year: int = 2025
    minimum_training_rows: int = 20
    transaction_cost_bps: float = 10.0
    random_seed: int = 847
    refresh: bool = False
    output_root: str | None = None
    snapshot_path: str | None = None

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ForecastRecord:
    prediction_id: str
    ticker: str
    prediction_timestamp: str
    knowledge_cutoff: str
    model: dict[str, Any]
    features: dict[str, float | None]
    prediction: dict[str, float]
    actual: dict[str, float]
    error: dict[str, float | bool]
    provenance: dict[str, Any]
    created_by: dict[str, str] = field(
        default_factory=lambda: {"experiment_version": EXPERIMENT_VERSION}
    )

    def to_json(self) -> dict[str, Any]:
        return asdict(self)
