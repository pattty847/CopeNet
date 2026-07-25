"""US Treasury yield-curve snapshot backed by the official Treasury feed."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Lock
from time import monotonic
from typing import Any, Literal

import pandas as pd

from .data_sources import TREASURY_YIELD_CURVE_URL, fetch_treasury_par_yield_history


YieldCurveRange = Literal["1d", "1w", "1m"]


@dataclass(frozen=True)
class TreasuryMaturity:
    label: str
    years: float
    symbol: str
    name: str


TREASURY_MATURITIES = (
    TreasuryMaturity("3M", 0.25, "BC_3MONTH", "3-month Constant Maturity Treasury"),
    TreasuryMaturity("2Y", 2.0, "BC_2YEAR", "2-year Constant Maturity Treasury"),
    TreasuryMaturity("5Y", 5.0, "BC_5YEAR", "5-year Constant Maturity Treasury"),
    TreasuryMaturity("10Y", 10.0, "BC_10YEAR", "10-year Constant Maturity Treasury"),
    TreasuryMaturity("30Y", 30.0, "BC_30YEAR", "30-year Constant Maturity Treasury"),
)

_RANGE_OFFSET: dict[YieldCurveRange, int] = {"1d": 1, "1w": 5, "1m": 21}
_CACHE_SECONDS = 15 * 60
_history_cache: tuple[float, pd.DataFrame] | None = None
_history_lock = Lock()


def fetch_treasury_yield_curve(selected_range: YieldCurveRange = "1d", *, refresh: bool = False) -> dict[str, Any]:
    """Fetch official Treasury CMT rates and derive curve spreads/interpretation."""
    symbols = [maturity.symbol for maturity in TREASURY_MATURITIES]
    closes = _load_treasury_history(refresh=refresh)
    available = [maturity for maturity in TREASURY_MATURITIES if maturity.symbol in closes and not closes[maturity.symbol].dropna().empty]
    available_symbols = [maturity.symbol for maturity in available]
    if "BC_3MONTH" not in available_symbols or "BC_10YEAR" not in available_symbols:
        raise RuntimeError("U.S. Treasury did not return the 3-month and 10-year anchor yields")
    common_closes = closes[available_symbols].dropna(how="any")
    offset = _RANGE_OFFSET[selected_range]
    if len(common_closes) <= offset:
        raise RuntimeError(f"U.S. Treasury did not return enough shared history for the {selected_range} comparison")
    current_row = common_closes.iloc[-1]
    previous_row = common_closes.iloc[-1 - offset]
    points = []
    for maturity in available:
        current = float(current_row[maturity.symbol])
        previous = float(previous_row[maturity.symbol])
        points.append(
            {
                "label": maturity.label,
                "years": maturity.years,
                "symbol": maturity.symbol,
                "name": maturity.name,
                "yield": round(current, 3),
                "changeBps": round((current - previous) * 100, 1),
            }
        )

    by_label = {point["label"]: point for point in points}
    spreads = _spreads(by_label)
    shape = _classify_shape(points, by_label)
    last_index = common_closes.index[-1]
    comparison_index = common_closes.index[-1 - offset]
    as_of = pd.to_datetime(last_index, utc=True).to_pydatetime().astimezone(timezone.utc)
    comparison_as_of = pd.to_datetime(comparison_index, utc=True).to_pydatetime().astimezone(timezone.utc)
    return {
        "status": "live",
        "source": "us-treasury",
        "sourceUrl": TREASURY_YIELD_CURVE_URL.format(year=as_of.year),
        "range": selected_range,
        "asOf": as_of.isoformat().replace("+00:00", "Z"),
        "comparisonAsOf": comparison_as_of.isoformat().replace("+00:00", "Z"),
        "points": points,
        "spreads": spreads,
        "shape": shape,
        "coverageNote": "Official daily par yields · U.S. Treasury Constant Maturity rates.",
    }


def _load_treasury_history(*, refresh: bool) -> pd.DataFrame:
    global _history_cache
    now = monotonic()
    with _history_lock:
        if not refresh and _history_cache and now - _history_cache[0] < _CACHE_SECONDS:
            return _history_cache[1].copy()
        year = datetime.now(timezone.utc).year
        history = fetch_treasury_par_yield_history(year)
        if len(history) <= max(_RANGE_OFFSET.values()):
            previous = fetch_treasury_par_yield_history(year - 1)
            history = pd.concat([previous, history]).sort_index()
            history = history[~history.index.duplicated(keep="last")]
        _history_cache = (now, history.copy())
        return history


def _spreads(by_label: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    pairs = (("10Y", "2Y"), ("10Y", "3M"))
    return [
        {
            "label": f"{long_label}–{short_label}",
            "valueBps": round((by_label[long_label]["yield"] - by_label[short_label]["yield"]) * 100, 1),
        }
        for long_label, short_label in pairs
        if long_label in by_label and short_label in by_label
    ]


def _classify_shape(points: list[dict[str, Any]], by_label: dict[str, dict[str, Any]]) -> dict[str, str]:
    short = by_label.get("3M", points[0])
    long = by_label.get("10Y", points[-1])
    slope_bps = (long["yield"] - short["yield"]) * 100
    slope_change_bps = long["changeBps"] - short["changeBps"]
    anchor_change = (short["changeBps"] + long["changeBps"]) / 2

    if slope_bps < -10:
        base = "Inverted"
        detail = "Short rates remain above the 10-year yield, a restrictive shape often watched for slowdown risk."
    elif slope_bps <= 25:
        base = "Flat"
        detail = "The 3-month and 10-year yields are close, signaling limited term premium and an uncertain path."
    else:
        base = "Normal"
        detail = "Long yields sit above short yields, restoring compensation for holding longer-duration debt."

    if abs(slope_change_bps) < 1:
        movement = "stable"
    else:
        direction = "steepening" if slope_change_bps > 0 else "flattening"
        prefix = "Bear" if anchor_change > 0 else "Bull" if anchor_change < 0 else "Curve"
        movement = f"{prefix} {direction.lower()}"
    return {"label": f"{base} · {movement}", "detail": detail}
