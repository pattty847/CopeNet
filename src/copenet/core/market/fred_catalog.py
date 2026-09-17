"""Curated FRED series definitions shared by snapshots and model tools."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal


FredTransform = Literal["native", "change", "yoy_pct"]


@dataclass(frozen=True)
class FredSeriesSpec:
    series_id: str
    label: str
    group: str
    interpretive_role: str
    transform: FredTransform = "native"
    expected_frequency: str = "unknown"

    def to_wire(self) -> dict:
        return asdict(self)


# A compact cross-cycle picture, not an attempt to mirror FRED's enormous catalog.
# Search and series tools cover the long tail.
CURATED_FRED_SERIES = (
    FredSeriesSpec("GDPC1", "Real GDP", "growth", "Real economic output", "yoy_pct", "quarterly"),
    FredSeriesSpec("INDPRO", "Industrial production", "growth", "Factory and utility output", "yoy_pct", "monthly"),
    FredSeriesSpec("PAYEMS", "Nonfarm payrolls", "labor", "Employment demand", "change", "monthly"),
    FredSeriesSpec("UNRATE", "Unemployment rate", "labor", "Labor-market slack", "native", "monthly"),
    FredSeriesSpec("ICSA", "Initial jobless claims", "labor", "High-frequency labor stress", "native", "weekly"),
    FredSeriesSpec("CPIAUCSL", "Consumer prices", "inflation", "Headline consumer inflation", "yoy_pct", "monthly"),
    FredSeriesSpec("CPILFESL", "Core consumer prices", "inflation", "Underlying consumer inflation", "yoy_pct", "monthly"),
    FredSeriesSpec("PCEPILFE", "Core PCE prices", "inflation", "Federal Reserve preferred core inflation", "yoy_pct", "monthly"),
    FredSeriesSpec("DFF", "Effective federal funds rate", "rates", "Current policy-rate transmission", "native", "daily"),
    FredSeriesSpec("T10Y2Y", "10-year minus 2-year spread", "rates", "Yield-curve growth signal", "native", "daily"),
    FredSeriesSpec("DFII10", "10-year real yield", "rates", "Real discount rate", "native", "daily"),
    FredSeriesSpec("BAMLH0A0HYM2", "High-yield credit spread", "credit", "Corporate credit stress", "native", "daily"),
    FredSeriesSpec("DRTSCILM", "Banks tightening C&I standards", "credit", "Bank lending restraint", "native", "quarterly"),
    FredSeriesSpec("STLFSI4", "Financial stress index", "credit", "Broad financial-system stress", "native", "weekly"),
    FredSeriesSpec("M2SL", "M2 money stock", "liquidity", "Broad money growth", "yoy_pct", "monthly"),
    FredSeriesSpec("WALCL", "Federal Reserve assets", "liquidity", "Central-bank balance-sheet liquidity", "yoy_pct", "weekly"),
    FredSeriesSpec("HOUST", "Housing starts", "housing", "Residential construction cycle", "yoy_pct", "monthly"),
    FredSeriesSpec("UMCSENT", "Consumer sentiment", "consumer", "Household confidence", "native", "monthly"),
)

CURATED_FRED_BY_ID = {spec.series_id: spec for spec in CURATED_FRED_SERIES}
