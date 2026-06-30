"""Base-rate calibration tables — the honesty layer of the Insight Engine.

A base rate answers: "when this pattern fired historically, what actually happened next?"
It calibrates the LANGUAGE of a descriptor against real outcomes (% up, median forward return, max
adverse excursion, benchmark-relative, regime split) — it does NOT optimize a strategy for alpha.

Tables are versioned by the feature-catalog version + pattern + horizon + universe, and persisted as
artifacts the briefing/UI can read by key. See docs/plans/MARKET_INSIGHT_ENGINE.md §9.
"""

from __future__ import annotations

import statistics
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .._json_store import read_json, write_json_atomic
from .features import FEATURE_CATALOG_VERSION


@dataclass(frozen=True)
class BaseRate:
    pattern: str
    horizon_weeks: int
    feature_catalog_version: str
    universe_id: str
    n: int
    pct_up: float
    median_fwd: float
    mean_fwd: float
    pct_beat_bench: float
    mean_mae: float  # mean max adverse excursion over the horizon (%)
    bull_n: int
    bull_pct_up: float
    bear_n: int
    bear_pct_up: float
    sample_start: str
    sample_end: str
    generated_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def headline(self) -> str:
        """Honest one-liner for the UI/LLM — always carries n."""
        if self.n < 5:
            return f"too few historical cases (n={self.n}) to state a base rate"
        return (
            f"historically resolved up {self.pct_up:.0f}% of the time over {self.horizon_weeks}w "
            f"(median {self.median_fwd:+.1f}%, n={self.n})"
        )


def build_base_rate(
    events: list[dict[str, Any]],
    *,
    pattern: str,
    horizon_weeks: int,
    universe_id: str,
    generated_at: str,
) -> BaseRate:
    """Aggregate point-in-time events (from replay) into a calibrated base rate.

    Each event dict must carry: fwd_return, mae, beat_bench (bool), regime ('bull'|'bear'),
    as_of (ISO date). Forward returns are produced in replay's separate label phase — never by the
    feature extractor.
    """
    n = len(events)
    if n == 0:
        return BaseRate(
            pattern, horizon_weeks, FEATURE_CATALOG_VERSION, universe_id, 0,
            0.0, 0.0, 0.0, 0.0, 0.0, 0, 0.0, 0, 0.0, "", "", generated_at,
        )
    fwd = [e["fwd_return"] for e in events]
    pct_up = sum(1 for r in fwd if r > 0) / n * 100
    pct_beat = sum(1 for e in events if e.get("beat_bench")) / n * 100
    bull = [e for e in events if e.get("regime") == "bull"]
    bear = [e for e in events if e.get("regime") == "bear"]
    dates = sorted(e["as_of"] for e in events)
    return BaseRate(
        pattern=pattern,
        horizon_weeks=horizon_weeks,
        feature_catalog_version=FEATURE_CATALOG_VERSION,
        universe_id=universe_id,
        n=n,
        pct_up=round(pct_up, 1),
        median_fwd=round(statistics.median(fwd), 2),
        mean_fwd=round(statistics.fmean(fwd), 2),
        pct_beat_bench=round(pct_beat, 1),
        mean_mae=round(statistics.fmean(e["mae"] for e in events), 2),
        bull_n=len(bull),
        bull_pct_up=round(sum(1 for e in bull if e["fwd_return"] > 0) / len(bull) * 100, 1) if bull else 0.0,
        bear_n=len(bear),
        bear_pct_up=round(sum(1 for e in bear if e["fwd_return"] > 0) / len(bear) * 100, 1) if bear else 0.0,
        sample_start=dates[0],
        sample_end=dates[-1],
        generated_at=generated_at,
    )


def _key(pattern: str, horizon_weeks: int) -> str:
    return f"{pattern}_{horizon_weeks}w_{FEATURE_CATALOG_VERSION}"


def base_rates_dir(root: Path | None = None) -> Path:
    base = root or (Path.home() / ".copenet" / "data" / "market" / "base_rates")
    base.mkdir(parents=True, exist_ok=True)
    return base


def save_base_rate(rate: BaseRate, *, root: Path | None = None) -> Path:
    path = base_rates_dir(root) / f"{_key(rate.pattern, rate.horizon_weeks)}.json"
    write_json_atomic(path, rate.to_dict())
    return path


def load_base_rate(pattern: str, horizon_weeks: int, *, root: Path | None = None) -> BaseRate | None:
    path = base_rates_dir(root) / f"{_key(pattern, horizon_weeks)}.json"
    payload = read_json(path, None)
    if not isinstance(payload, dict):
        return None
    if payload.get("feature_catalog_version") != FEATURE_CATALOG_VERSION:
        return None  # stale against current feature math
    try:
        return BaseRate(**payload)
    except TypeError:
        return None
