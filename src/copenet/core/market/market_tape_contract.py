"""Versioned DTOs for a frozen, account-neutral market-tape observation."""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from typing import Any


MARKET_TAPE_SCHEMA_VERSION = "market_tape.v1"
MARKET_TAPE_BAR_WINDOW = 15


def _camel(name: str) -> str:
    parts = name.split("_")
    return parts[0] + "".join(part[:1].upper() + part[1:] for part in parts[1:])


def _wire(value: Any) -> Any:
    if is_dataclass(value):
        return {_camel(key): _wire(item) for key, item in asdict(value).items() if item is not None}
    if isinstance(value, (list, tuple)):
        return [_wire(item) for item in value]
    if isinstance(value, dict):
        return {_camel(str(key)): _wire(item) for key, item in value.items() if item is not None}
    return value


@dataclass(frozen=True)
class TapeBar:
    date: str
    timestamp: int
    complete: bool
    geometry_valid: bool
    open: float
    high: float
    low: float
    close: float
    volume: int
    return_pct: float | None
    gap_pct: float | None
    range_atr: float | None
    body_atr: float | None
    upper_wick_atr: float | None
    lower_wick_atr: float | None
    close_location_pct: float | None
    volume_vs_20d: float | None


@dataclass(frozen=True)
class TapeSummary:
    return_1d_pct: float | None
    return_2d_pct: float | None
    return_5d_pct: float | None
    atr_pct: float | None
    realized_vol_20d_pct: float | None
    dist_ma20_atr: float | None
    dist_ma50_atr: float | None
    volume_vs_20d: float | None


@dataclass(frozen=True)
class TapeInstrument:
    symbol: str
    role: str
    timeframe: str
    price_basis: str
    latest_bar_complete: bool
    summary: TapeSummary
    bars: list[TapeBar]


@dataclass(frozen=True)
class TrendObservation:
    symbol: str
    state: str | None
    prior_state: str | None
    weeks_in_state: int
    slope_40_atr: float | None
    distance_40_atr: float | None
    current_week_complete: bool


@dataclass(frozen=True)
class ParticipationSnapshot:
    index_positive: int
    index_negative: int
    index_transition: int
    sector_positive: int
    sector_negative: int
    sector_transition: int
    equal_weight_excess_5d_pct: float | None
    small_cap_excess_5d_pct: float | None
    index_states: list[TrendObservation]
    sector_states: list[TrendObservation]


@dataclass(frozen=True)
class RrgVector:
    x: float
    y: float
    delta_x: float | None
    delta_y: float | None
    velocity: float | None


@dataclass(frozen=True)
class RrgObservation:
    symbol: str
    group: str
    quadrant: str
    modes: dict[str, RrgVector]


@dataclass(frozen=True)
class RiskPlumbingSnapshot:
    high_yield_excess_5d_pct: float | None
    volatility_1d_pct: float | None
    volatility_5d_pct: float | None
    long_duration_5d_pct: float | None
    dollar_5d_pct: float | None
    gold_5d_pct: float | None


@dataclass(frozen=True)
class TapeDataQuality:
    required_symbols: int
    available_symbols: int
    missing_symbols: list[str]
    potentially_incomplete_daily_symbols: list[str]
    potentially_incomplete_weekly_symbols: list[str]
    malformed_daily_symbols: list[str]
    source_age_minutes: float
    warnings: list[str]


@dataclass(frozen=True)
class MarketTapePacket:
    schema_version: str
    generated_at: str
    observed_at: str
    completed_through: str | None
    price_basis: str
    instruments: list[TapeInstrument]
    participation: ParticipationSnapshot
    rrg: list[RrgObservation]
    risk_plumbing: RiskPlumbingSnapshot
    data_quality: TapeDataQuality

    def to_wire(self) -> dict[str, Any]:
        return _wire(self)
