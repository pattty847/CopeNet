"""Market participation: how much of the listed market is actually trending.

This is the number the dashboard's "breadth" was never measuring. That one divides by
the operator's own holdings, watchlist and speculative positions (universe.SIGNAL_ROLES),
so it reports whether names already chosen are doing well — a portfolio health score,
structurally biased toward the picks. Participation divides by a market population
defined without reference to the operator.

Three tests run over the same bars in one evaluator pass, because nobody knows which
definition of "healthy" is the right one and they are nearly free together:

    above 50-day average    conventional, fast, whipsaws on the line
    above 200-day average   conventional, slow, the standard trend filter
    MAMA above FAMA         Ehlers' adaptive crossover, no fixed lookback

Only the two moving-average counts have published equivalents to check against. The
MAMA count has no external reference, so a bug in it would simply look like a number.

Everything here is a present-day cross-section. The archive holds no delisted names,
which is correct for "what is participating today" and disqualifying for anything
historical — see the package docstring.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from ..alert_evaluator import evaluator_request
from .store import STOOQ_BASIS, StooqArchive, StooqBar

# A market population, not a stock picker's list: common stocks (Stooq separates funds
# into their own folders) that actually trade. Below roughly ten million dollars a day
# the tape is thin enough that a moving-average cross says more about one block trade
# than about participation.
DEFAULT_MIN_DOLLAR_VOLUME = 10_000_000.0
DEFAULT_LIQUIDITY_WINDOW = 60
MIN_BARS = 260

# Uniform for every symbol so the cross-section is comparable. Three years leaves the
# 200-day average a long runway and gives MAMA's recursion time to settle well before
# the reading we take. These are recursive filters whose value depends on their seed,
# so an inconsistent lookback would make names incomparable to each other.
LOOKBACK_BARS = 756

_CHUNK_BUDGET_BYTES = 4_000_000

_SPECS = [
    {"indicatorId": "sma", "config": {"period": 50}, "label": "ma50"},
    {"indicatorId": "sma", "config": {"period": 200}, "label": "ma200"},
    {"indicatorId": "mama", "config": {}, "label": "mama"},
    {"indicatorId": "atr", "config": {"period": 14}, "label": "atr"},
]


@dataclass(frozen=True)
class SymbolReading:
    symbol: str
    close: float
    above_ma50: bool | None
    above_ma200: bool | None
    mama_above_fama: bool | None
    # Sign carries direction, magnitude carries conviction. Normalising the MAMA/FAMA
    # spread by ATR is what makes it comparable across a $4 stock and a $900 one.
    mama_spread_atr: float | None


@dataclass(frozen=True)
class Participation:
    basis: str
    as_of: int | None
    universe: int
    read: int
    readings: list[SymbolReading] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)

    def _share(self, attribute: str) -> tuple[float | None, int]:
        values = [getattr(row, attribute) for row in self.readings]
        counted = [value for value in values if value is not None]
        if not counted:
            return None, 0
        return 100.0 * sum(1 for value in counted if value) / len(counted), len(counted)

    def summary(self) -> dict[str, Any]:
        """Percentages that always ship their own denominator.

        A participation figure without its coverage is unreadable: 47% of 2,400 names and
        47% of 300 names are different claims, and a fetch that silently lost most of the
        universe looks exactly like a market that narrowed.
        """
        out: dict[str, Any] = {
            "basis": self.basis,
            "asOf": self.as_of,
            "universe": self.universe,
            "read": self.read,
            "errors": len(self.errors),
        }
        for name, attribute in (
            ("pctAboveMa50", "above_ma50"),
            ("pctAboveMa200", "above_ma200"),
            ("pctMamaAboveFama", "mama_above_fama"),
        ):
            share, counted = self._share(attribute)
            out[name] = None if share is None else round(share, 1)
            out[f"{name}Counted"] = counted
        return out


def select_universe(
    archive: StooqArchive,
    *,
    min_dollar_volume: float = DEFAULT_MIN_DOLLAR_VOLUME,
    window: int = DEFAULT_LIQUIDITY_WINDOW,
    min_bars: int = MIN_BARS,
) -> list[str]:
    """Liquid common stocks, by median dollar volume over the recent window.

    Median rather than mean: one earnings-day volume spike should not admit a name that
    is otherwise untraded, and that is common enough among small caps to matter.
    """
    selected: list[str] = []
    for symbol in sorted(archive.equities):
        bars = archive.read(symbol, limit=max(min_bars, window))
        if len(bars) < min_bars:
            continue
        recent = bars[-window:]
        turnover = sorted(bar.close * bar.volume for bar in recent)
        if len(turnover) < window // 2:
            continue
        median = turnover[len(turnover) // 2]
        if median >= min_dollar_volume:
            selected.append(symbol)
    return selected


def _request(symbol: str, bars: list[StooqBar]) -> dict[str, Any]:
    return {
        "key": symbol,
        "bars": [
            {"t": bar.date, "o": bar.open, "h": bar.high, "l": bar.low, "c": bar.close, "v": bar.volume}
            for bar in bars
        ],
        "indicators": _SPECS,
    }


def _reading(symbol: str, close: float, values: dict[str, Any]) -> SymbolReading:
    ma50 = (values.get("ma50") or {}).get("value")
    ma200 = (values.get("ma200") or {}).get("value")
    mama = (values.get("mama") or {}).get("mama")
    fama = (values.get("mama") or {}).get("fama")
    atr = (values.get("atr") or {}).get("atr")
    spread = None
    if mama is not None and fama is not None and atr:
        spread = (mama - fama) / atr
    return SymbolReading(
        symbol=symbol,
        close=close,
        above_ma50=None if ma50 is None else close > ma50,
        above_ma200=None if ma200 is None else close > ma200,
        mama_above_fama=None if mama is None or fama is None else mama >= fama,
        mama_spread_atr=spread,
    )


def compute_participation(
    archive: StooqArchive,
    symbols: list[str],
    *,
    lookback: int = LOOKBACK_BARS,
) -> Participation:
    """Read every symbol once, evaluate in chunked batches, count what came back."""
    readings: list[SymbolReading] = []
    errors: dict[str, str] = {}
    as_of: int | None = None
    chunk: list[dict[str, Any]] = []
    closes: dict[str, float] = {}
    size = 0

    def flush() -> None:
        nonlocal chunk, size
        if not chunk:
            return
        try:
            response = evaluator_request(
                {"action": "latest", "timeframe": "daily", "requests": chunk}
            )
        except ValueError as exc:
            errors.update({request["key"]: str(exc) for request in chunk})
            chunk, size = [], 0
            return
        returned = {str(row.get("key")): row for row in response.get("results") or []}
        for request in chunk:
            row = returned.get(request["key"])
            if row is None or row.get("error"):
                errors[request["key"]] = (row or {}).get("error") or "no result returned"
                continue
            readings.append(_reading(request["key"], closes[request["key"]], row.get("values") or {}))
        chunk, size = [], 0

    for symbol in symbols:
        bars = archive.read(symbol, limit=lookback)
        if len(bars) < 2:
            errors[symbol] = "no usable history"
            continue
        closes[symbol] = bars[-1].close
        as_of = bars[-1].date if as_of is None else max(as_of, bars[-1].date)
        request = _request(symbol, bars)
        cost = len(json.dumps(request, allow_nan=False))
        if chunk and size + cost > _CHUNK_BUDGET_BYTES:
            flush()
        chunk.append(request)
        size += cost
    flush()

    return Participation(
        basis=STOOQ_BASIS,
        as_of=as_of,
        universe=len(symbols),
        read=len(readings),
        readings=readings,
        errors=errors,
    )
