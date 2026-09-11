"""Boundary configuration and versioned, inspectable screener definitions."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

VERSION = 1
MAX_ROWS = 5000


class ScreenerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)
    minCap: float = Field(default=10e9, ge=1e9, le=20e12)
    maxCap: float | None = Field(default=None, ge=1e9, le=20e12)
    minPrice: float = Field(default=10, ge=5, le=10000)
    minDollarVolume: float = Field(default=25e6, ge=5e6, le=10e9)

    @model_validator(mode="after")
    def valid_range(self):
        if self.maxCap is not None and self.maxCap < self.minCap:
            raise ValueError("Maximum market cap must be at least the minimum")
        return self


PRESETS = [
    {"id": "compression", "name": "Compression", "direction": "Either", "metric": "bandWidth",
     "ascending": True, "description": "Tight daily bands near the annual high; watch for expansion in either direction.",
     "rules": ["20-day Bollinger width ≤ 10% of price", "Within 10% of 52-week high", "RSI 40–65"],
     "next": "Inspect the base and volume history. A narrow band alone does not establish a contraction sequence or breakout direction."},
    {"id": "pullback", "name": "Leader pullback", "direction": "Bullish", "metric": "distance50",
     "ascending": True, "description": "An established uptrend testing its 50-day average after a modest retreat.",
     "rules": ["Price > SMA200 and SMA50 > SMA200", "Price −2% to +4% from SMA50", "3–15% below 52-week high; RSI 40–60"],
     "next": "Check whether support holds and compare with the sector. Trend alignment does not measure benchmark-relative strength."},
    {"id": "oversold", "name": "Oversold large caps", "direction": "Bullish", "metric": "rsi",
     "ascending": True, "description": "Liquid companies under sustained pressure, for rebound research.",
     "rules": ["Market cap ≥ $15B (or your higher minimum)", "15–40% below 52-week high", "RSI 25–38"],
     "next": "Review filings, earnings and balance-sheet changes before a rebound thesis. Oversold can remain oversold."},
    {"id": "breakdown", "name": "Breakdown watch", "direction": "Bearish", "metric": "distance200",
     "ascending": True, "description": "Weak trend structure with negative monthly momentum, before extreme oversold conditions.",
     "rules": ["Price < SMA50 < SMA200", "RSI 30–48", "One-month return < 0%; price no more than 15% below SMA200"],
     "next": "Inspect failed support, catalysts and downside levels. Borrow availability and short-sale costs are not screened."},
    {"id": "expansion", "name": "Volume expansion", "direction": "Either", "metric": "relativeVolume",
     "ascending": False, "description": "Unusual activity with a meaningful move up or down, capped to avoid chasing extreme spikes.",
     "rules": ["Relative volume ≥ 1.5×", "Absolute daily change 2–10%"],
     "next": "Verify the catalyst and follow-through. Daily relative volume is not time-of-day adjusted or proof of institutional flow."},
]
