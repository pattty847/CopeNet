"""Durable intraday bar cache — one file per (symbol, grain).

Deliberately its own store, not part of `PriceCache`. `MARKET_SENTINEL_ALERTS.md` §3 rule 2
forbids intraday entering the `(symbol, timeframe)` MarketStore, and rule 3 fixes the key:
vendor, symbol, interval, timestamp, session, adjustment basis.

Session is the one part of that key held differently, on purpose. CopeNet stores the
SUPERSET — every bar the vendor returns, regular and extended — and derives each bar's
session from its own timestamp on read. Two caches keyed by session would hold the same
regular-hours bars twice and could disagree; one superset cannot.

It borrows the daily cache's central rule, because the rule is about vendors and not about
timeframes:

    dividends never invalidate the cache; splits always do.

A split rewrites Yahoo's own history, so every stored bar sits on a stale basis and the
symbol must be rebuilt. The daily lane already detects splits on its delta fetch, so this
store consumes that fingerprint rather than running a second detector.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time, timezone
from pathlib import Path
import threading
from zoneinfo import ZoneInfo

from copenet.core._json_store import read_json, write_json_atomic

from ..models import MarketBar

CACHE_VERSION = 1
VENDOR = "yahoo"
BASIS = "split_adjusted"

EXCHANGE = ZoneInfo("America/New_York")
REGULAR_OPEN = time(9, 30)
REGULAR_CLOSE = time(16, 0)

REGULAR = "regular"
EXTENDED = "extended"
ALL_SESSIONS = "all"


def bar_session(timestamp: int) -> str:
    """Which session a bar belongs to, derived from its own timestamp.

    Derived rather than stored: a stored field can disagree with the timestamp it describes,
    and then two readers of the same bar reach different conclusions. This cannot.
    """
    local = datetime.fromtimestamp(int(timestamp), tz=EXCHANGE).timetz()
    return REGULAR if REGULAR_OPEN <= local.replace(tzinfo=None) < REGULAR_CLOSE else EXTENDED


def filter_session(bars: list[MarketBar], session: str) -> list[MarketBar]:
    if session == ALL_SESSIONS:
        return list(bars)
    if session not in (REGULAR, EXTENDED):
        raise ValueError(f"unknown session: {session!r}")
    return [bar for bar in bars if bar_session(int(bar.t)) == session]


@dataclass(frozen=True)
class IntradayHistory:
    """One symbol at one native grain. `bars` are split-only and span every session."""

    symbol: str
    grain: str
    bars: list[MarketBar] = field(default_factory=list)
    split_fingerprint: str = ""
    updated_at: str = ""

    @property
    def covered_from(self) -> int | None:
        return int(self.bars[0].t) if self.bars else None

    @property
    def covered_through(self) -> int | None:
        return int(self.bars[-1].t) if self.bars else None


def merge_bars(existing: list[MarketBar], incoming: list[MarketBar]) -> list[MarketBar]:
    """Later data wins on collision.

    The vendor revises recent intraday bars — a 15:59 candle fetched at 16:00 is not the one
    it reports an hour later. Blind append would keep the first version forever and leave the
    cache quietly disagreeing with the vendor about the most recent session, which is the one
    an operator is most likely to be looking at.
    """
    by_time: dict[int, MarketBar] = {int(bar.t): bar for bar in existing}
    by_time.update({int(bar.t): bar for bar in incoming})
    return [by_time[key] for key in sorted(by_time)]


class IntradayStore:
    """Thread-safe on-disk intraday history, one JSON file per symbol and grain."""

    def __init__(self, root_dir: Path) -> None:
        self._root = root_dir
        self._root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def path_for(self, symbol: str, grain: str) -> Path:
        safe = "".join(char for char in symbol.upper() if char.isalnum() or char in "-._^")
        if not safe:
            raise ValueError(f"invalid symbol: {symbol!r}")
        return self._root / f"{safe}.{grain}.json"

    def load(self, symbol: str, grain: str) -> IntradayHistory | None:
        path = self.path_for(symbol, grain)
        with self._lock:
            raw = read_json(path, fallback=None)
        if not isinstance(raw, dict):
            return None
        # A cache written by an older layout, a different vendor, or a different adjustment
        # basis is not this cache. Treat it as absent rather than reinterpreting it.
        if raw.get("version") != CACHE_VERSION or raw.get("vendor") != VENDOR or raw.get("basis") != BASIS:
            return None
        rows = raw.get("bars")
        bars = [
            MarketBar(t=int(row["t"]), o=float(row["o"]), h=float(row["h"]),
                      l=float(row["l"]), c=float(row["c"]), v=int(row.get("v") or 0))
            for row in rows if isinstance(row, dict) and "t" in row
        ] if isinstance(rows, list) else []
        return IntradayHistory(
            symbol=str(raw.get("symbol") or symbol).upper(),
            grain=str(raw.get("grain") or grain),
            bars=sorted(bars, key=lambda bar: int(bar.t)),
            split_fingerprint=str(raw.get("splitFingerprint") or ""),
            updated_at=str(raw.get("updatedAt") or ""),
        )

    def save(self, history: IntradayHistory) -> IntradayHistory:
        stamped = IntradayHistory(
            symbol=history.symbol, grain=history.grain, bars=history.bars,
            split_fingerprint=history.split_fingerprint,
            updated_at=datetime.now(timezone.utc).isoformat(),
        )
        with self._lock:
            write_json_atomic(self.path_for(stamped.symbol, stamped.grain), {
                "version": CACHE_VERSION,
                "vendor": VENDOR,
                "basis": BASIS,
                "symbol": stamped.symbol,
                "grain": stamped.grain,
                "splitFingerprint": stamped.split_fingerprint,
                "updatedAt": stamped.updated_at,
                "bars": [{"t": bar.t, "o": bar.o, "h": bar.h, "l": bar.l, "c": bar.c, "v": bar.v}
                         for bar in stamped.bars],
            })
        return stamped

    def merge(self, symbol: str, grain: str, incoming: list[MarketBar], *, split_fingerprint: str) -> IntradayHistory:
        """Fold a fetch into the cache, rebuilding from scratch when a split has landed."""
        existing = self.load(symbol, grain)
        stale_basis = existing is not None and existing.split_fingerprint != split_fingerprint
        bars = list(incoming) if (existing is None or stale_basis) else merge_bars(existing.bars, incoming)
        return self.save(IntradayHistory(
            symbol=symbol.upper(), grain=grain, bars=bars, split_fingerprint=split_fingerprint,
        ))

    def drop(self, symbol: str, grain: str) -> bool:
        path = self.path_for(symbol, grain)
        with self._lock:
            if not path.exists():
                return False
            path.unlink()
        return True
