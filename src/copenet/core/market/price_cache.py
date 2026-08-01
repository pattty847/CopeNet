"""Durable append-only daily price cache — the single source of candle history.

Before this existed, opening one ticker fired roughly eight yfinance requests and the
morning dashboard refresh fired two per symbol across the universe, all re-downloading
history that had not changed in years.

The cache stores split-only daily bars plus the split and dividend histories, and derives
weekly/monthly candles and total-return prices at read time (see `price_history`). The
rule that makes it safe to append to:

    dividends never invalidate the cache; splits always do.

A dividend only shifts *derived* total-return prices, which are computed on read. A split
rewrites Yahoo's own history for the symbol, so every stored bar is on a stale basis and
that symbol must be rebuilt from scratch. Split detection rides along on the delta fetch:
a six-month window carries any recent split, and anything older is already recorded.

Full design and migration status: `docs/plans/PRICE_CACHE.md`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import threading
from typing import Any, Callable

from copenet.core._json_store import read_json, write_json_atomic

from .data_sources import fetch_daily_price_history, frame_to_bars
from .models import MarketBar
from .price_history import (
    DAILY,
    SPLIT_ADJUSTED,
    derive_bars,
    merge_actions,
    merge_daily_bars,
    split_fingerprint,
)


CACHE_VERSION = 1
STORED_PRICE_BASIS = SPLIT_ADJUSTED
#: Delta window. Wide enough that a split cannot slip through between refreshes, small
#: enough to stay a cheap request (~125 rows).
DELTA_PERIOD = "6mo"
#: Skip the network entirely for a cache younger than this. Callers wanting a live
#: current candle during market hours should pass something shorter.
DEFAULT_MAX_AGE_SECONDS = 900

FetchDailyHistory = Callable[..., tuple[Any, list[tuple[str, float]], list[tuple[str, float]]]]


@dataclass(frozen=True)
class PriceHistory:
    """One symbol's stored history. `bars` are daily and split-only."""

    symbol: str
    bars: list[MarketBar]
    splits: list[tuple[str, float]]
    dividends: list[tuple[str, float]]
    updated_at: str

    def derive(self, *, timeframe: str = DAILY, basis: str = SPLIT_ADJUSTED) -> list[MarketBar]:
        return derive_bars(self.bars, self.dividends, timeframe=timeframe, basis=basis)


class PriceCache:
    """Thread-safe on-disk daily price history, one JSON file per symbol."""

    def __init__(
        self,
        root_dir: Path,
        *,
        fetch: FetchDailyHistory | None = None,
    ) -> None:
        self._root = Path(root_dir)
        self._root.mkdir(parents=True, exist_ok=True)
        # Resolved per call rather than bound here so module-level patching works
        # regardless of when a cache was constructed — the offline test fixtures depend
        # on being able to cut the network after a runtime already exists.
        self._fetch = fetch
        self._lock = threading.RLock()

    def _fetch_history(self, symbol: str, *, period: str):
        return (self._fetch or fetch_daily_price_history)(symbol, period=period)

    @property
    def root_dir(self) -> Path:
        return self._root

    def load(self, symbol: str) -> PriceHistory | None:
        """Read stored history without touching the network. None when nothing is cached."""
        payload = read_json(self._path(symbol), {})
        if not isinstance(payload, dict):
            return None
        if payload.get("cacheVersion") != CACHE_VERSION:
            return None
        if payload.get("priceBasis") != STORED_PRICE_BASIS:
            return None
        bars = _bars_from_wire(payload.get("bars"))
        if not bars:
            return None
        return PriceHistory(
            symbol=str(payload.get("symbol") or symbol).upper(),
            bars=bars,
            splits=_actions_from_wire(payload.get("splits")),
            dividends=_actions_from_wire(payload.get("dividends")),
            updated_at=str(payload.get("updatedAt") or ""),
        )

    def bars(
        self,
        symbol: str,
        *,
        timeframe: str = DAILY,
        basis: str = SPLIT_ADJUSTED,
    ) -> list[MarketBar]:
        """Cached candles at a timeframe and basis. Empty when nothing is cached."""
        history = self.load(symbol)
        return history.derive(timeframe=timeframe, basis=basis) if history else []

    def refresh(
        self,
        symbol: str,
        *,
        max_age_seconds: float = DEFAULT_MAX_AGE_SECONDS,
        force: bool = False,
        now: datetime | None = None,
    ) -> PriceHistory | None:
        """Bring a symbol up to date, doing the least network work that is correct.

        Returns the stored history, or None when nothing is cached and the fetch failed —
        callers must treat that as "no data", never as "no history exists".
        """
        normalized = symbol.strip().upper()
        if not normalized:
            raise ValueError("symbol is required")
        moment = now or datetime.now(timezone.utc)
        cached = self.load(normalized)
        if cached and not force and _age_seconds(cached.updated_at, moment) < max_age_seconds:
            return cached
        if cached is None or force:
            return self._rebuild(normalized, moment)

        frame, splits, dividends = self._fetch_history(normalized, period=DELTA_PERIOD)
        incoming = frame_to_bars(frame)
        if not incoming:
            return cached
        if split_fingerprint(splits) and not _splits_are_known(splits, cached.splits):
            # Yahoo has rewritten this symbol's whole history onto a new share basis.
            # Merging would glue pre-split and post-split prices together — the exact
            # corruption the auto_adjust invariant exists to prevent.
            return self._rebuild(normalized, moment)
        return self._write(
            PriceHistory(
                symbol=normalized,
                bars=merge_daily_bars(cached.bars, incoming),
                splits=merge_actions(cached.splits, splits),
                dividends=merge_actions(cached.dividends, dividends),
                updated_at=moment.isoformat(),
            )
        )

    def _rebuild(self, symbol: str, moment: datetime) -> PriceHistory | None:
        frame, splits, dividends = self._fetch_history(symbol, period="max")
        bars = frame_to_bars(frame)
        if not bars:
            return self.load(symbol)
        return self._write(
            PriceHistory(
                symbol=symbol,
                bars=bars,
                splits=merge_actions([], splits),
                dividends=merge_actions([], dividends),
                updated_at=moment.isoformat(),
            )
        )

    def _write(self, history: PriceHistory) -> PriceHistory:
        payload = {
            "symbol": history.symbol,
            "cacheVersion": CACHE_VERSION,
            "priceBasis": STORED_PRICE_BASIS,
            "updatedAt": history.updated_at,
            "splitFingerprint": split_fingerprint(history.splits),
            "splits": [[day, ratio] for day, ratio in history.splits],
            "dividends": [[day, amount] for day, amount in history.dividends],
            "bars": [bar.__dict__ for bar in history.bars],
        }
        with self._lock:
            write_json_atomic(self._path(history.symbol), payload)
        return history

    def _path(self, symbol: str) -> Path:
        return self._root / f"{symbol.strip().upper()}.json"


def _splits_are_known(
    incoming: list[tuple[str, float]],
    known: list[tuple[str, float]],
) -> bool:
    recorded = {(str(day), round(float(ratio), 6)) for day, ratio in known}
    return all((str(day), round(float(ratio), 6)) in recorded for day, ratio in incoming)


def _age_seconds(updated_at: str, moment: datetime) -> float:
    if not updated_at:
        return float("inf")
    try:
        stamp = datetime.fromisoformat(updated_at)
    except ValueError:
        return float("inf")
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return (moment - stamp).total_seconds()


def _bars_from_wire(rows: Any) -> list[MarketBar]:
    if not isinstance(rows, list):
        return []
    bars: list[MarketBar] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            bars.append(
                MarketBar(
                    t=int(row["t"]),
                    o=float(row["o"]),
                    h=float(row["h"]),
                    l=float(row["l"]),
                    c=float(row["c"]),
                    v=int(row["v"]),
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    return sorted(bars, key=lambda bar: bar.t)


def _actions_from_wire(rows: Any) -> list[tuple[str, float]]:
    if not isinstance(rows, list):
        return []
    actions: list[tuple[str, float]] = []
    for row in rows:
        if not isinstance(row, (list, tuple)) or len(row) != 2:
            continue
        try:
            actions.append((str(row[0]), float(row[1])))
        except (TypeError, ValueError):
            continue
    return sorted(actions)
