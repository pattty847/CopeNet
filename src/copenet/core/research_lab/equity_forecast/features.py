"""Deterministic feature derivation and feature-set declarations."""

from __future__ import annotations

import math
from typing import Any

import pandas as pd


FUNDAMENTAL_SERIES: dict[str, str] = {
    "diluted_eps": "ttm",
    "revenue": "ttm",
    "operating_income": "ttm",
    "fcf": "ttm",
    "gross_margin": "ttm",
    "operating_margin": "ttm",
    "fcf_margin": "ttm",
    "rnd_intensity": "ttm",
    "sbc_burden": "ttm",
    "capex_intensity": "ttm",
    "roic": "ttm",
    "interest_coverage": "ttm",
    "net_debt": "quarterly",
    "working_capital": "quarterly",
}

GROWTH_FEATURES = (
    "revenue_growth_1y",
    "revenue_cagr_3y",
    "operating_income_growth_1y",
    "fcf_growth_1y",
)
QUALITY_FEATURES = (
    "gross_margin",
    "operating_margin",
    "operating_margin_change_1y",
    "fcf_margin",
    "fcf_margin_change_1y",
    "rnd_intensity",
    "sbc_to_revenue",
    "capex_to_revenue",
    "roic",
    "roic_change_1y",
    "interest_coverage",
    "net_debt_to_fcf",
    "working_capital_to_revenue",
)
VALUATION_FEATURES = ("trailing_pe",)
MOMENTUM_FEATURES = ("momentum_6m", "momentum_12m", "volatility_12m")
FUNDAMENTAL_FEATURES = GROWTH_FEATURES + QUALITY_FEATURES

FEATURE_SETS: dict[str, tuple[str, ...]] = {
    "fundamentals_only": FUNDAMENTAL_FEATURES,
    "fundamentals_plus_market": FUNDAMENTAL_FEATURES + VALUATION_FEATURES + MOMENTUM_FEATURES,
    "fundamentals_without_valuation": FUNDAMENTAL_FEATURES + MOMENTUM_FEATURES,
    "valuation_only": VALUATION_FEATURES,
    "growth_only": GROWTH_FEATURES,
    "quality_profitability_only": QUALITY_FEATURES,
}


def safe_ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or not math.isfinite(denominator) or abs(denominator) < 1e-12:
        return None
    value = numerator / denominator
    return value if math.isfinite(value) else None


def growth(current: float | None, prior: float | None) -> float | None:
    ratio = safe_ratio(current, prior)
    return None if ratio is None else ratio - 1.0


def cagr(current: float | None, prior: float | None, years: float) -> float | None:
    if current is None or prior is None or current <= 0 or prior <= 0 or years <= 0:
        return None
    return (current / prior) ** (1.0 / years) - 1.0


def latest_at_or_before(observations: list[dict[str, Any]], period_end: str, *, tolerance_days: int = 120) -> float | None:
    eligible = [row for row in observations if str(row.get("periodEnd") or "") <= period_end]
    if not eligible:
        return None
    selected = max(eligible, key=lambda row: (str(row.get("periodEnd")), str(row.get("availableAt"))))
    age = (pd.Timestamp(period_end) - pd.Timestamp(selected["periodEnd"])).days
    if age < 0 or age > tolerance_days:
        return None
    value = selected.get("value")
    return float(value) if value is not None else None


def derive_fundamental_features(series: dict[str, list[dict[str, Any]]]) -> dict[str, float | None]:
    latest_rows = [row for rows in series.values() for row in rows]
    if not latest_rows:
        return {name: None for name in FUNDAMENTAL_FEATURES}
    latest_period = max(str(row.get("periodEnd") or "") for row in latest_rows)
    latest_year = int(latest_period[:4])

    def value(metric: str, years_back: int = 0) -> float | None:
        cutoff = f"{latest_year - years_back:04d}{latest_period[4:]}"
        return latest_at_or_before(series.get(metric, []), cutoff)

    revenue, fcf = value("revenue"), value("fcf")
    operating_margin, fcf_margin, roic = value("operating_margin"), value("fcf_margin"), value("roic")
    return {
        "revenue_growth_1y": growth(revenue, value("revenue", 1)),
        "revenue_cagr_3y": cagr(revenue, value("revenue", 3), 3),
        "operating_income_growth_1y": growth(value("operating_income"), value("operating_income", 1)),
        "fcf_growth_1y": growth(fcf, value("fcf", 1)),
        "gross_margin": value("gross_margin"),
        "operating_margin": operating_margin,
        "operating_margin_change_1y": None if operating_margin is None or value("operating_margin", 1) is None else operating_margin - value("operating_margin", 1),
        "fcf_margin": fcf_margin,
        "fcf_margin_change_1y": None if fcf_margin is None or value("fcf_margin", 1) is None else fcf_margin - value("fcf_margin", 1),
        "rnd_intensity": value("rnd_intensity"),
        "sbc_to_revenue": value("sbc_burden"),
        "capex_to_revenue": value("capex_intensity"),
        "roic": roic,
        "roic_change_1y": None if roic is None or value("roic", 1) is None else roic - value("roic", 1),
        "interest_coverage": value("interest_coverage"),
        "net_debt_to_fcf": safe_ratio(value("net_debt"), fcf),
        "working_capital_to_revenue": safe_ratio(value("working_capital"), revenue),
    }
