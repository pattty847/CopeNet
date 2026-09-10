"""Serving one intraday interval: cache, refresh, roll up, filter.

The read path the chart uses. It exists so no caller has to know that `15m` is stored as
`5m`, that `1m` arrives in pages, or that the session split is derived rather than stored.

Freshness, not schedules. The lane refreshes when the cache is older than the interval it is
serving, because a 1h chart has nothing new to say sixty seconds later while a 1m chart does.
Nothing here polls; a read either finds the cache fresh enough or fetches once.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging

from ..models import MarketBar
from ..price_history import split_fingerprint
from .fetch import fetch_grain
from .intervals import interval_seconds, resolve
from .resample import resample_intraday
from .store import ALL_SESSIONS, IntradayStore, filter_session

logger = logging.getLogger(__name__)

#: A cache is stale once it is older than the bar it serves — capped, because a 1h chart does
#: not need a network round trip every hour of a session it is not watching.
MIN_REFRESH_SECONDS = 60
MAX_REFRESH_SECONDS = 900


@dataclass
class IntradaySeries:
    """One interval, ready to draw, plus everything the caller needs to be honest about it."""

    symbol: str
    interval: str
    session: str
    bars: list[MarketBar]
    #: The grain actually fetched. `15m` says `5m` here, which is not an implementation
    #: detail to the operator: it is why the interval reaches 60 days and not 30.
    grain: str
    window_days: int
    fetched: bool = False
    requests: int = 0
    warnings: list[str] = field(default_factory=list)
    unavailable: str | None = None
    updated_at: str = ""

    @property
    def covered_from(self) -> int | None:
        return int(self.bars[0].t) if self.bars else None

    @property
    def covered_through(self) -> int | None:
        return int(self.bars[-1].t) if self.bars else None

    def to_wire(self) -> dict:
        return {
            "symbol": self.symbol,
            "interval": self.interval,
            "session": self.session,
            "grain": self.grain,
            "windowDays": self.window_days,
            "bars": [{"t": bar.t, "o": bar.o, "h": bar.h, "l": bar.l, "c": bar.c, "v": bar.v}
                     for bar in self.bars],
            "coveredFrom": self.covered_from,
            "coveredThrough": self.covered_through,
            "fetched": self.fetched,
            "requests": self.requests,
            "warnings": list(self.warnings),
            "unavailable": self.unavailable,
            "updatedAt": self.updated_at,
        }


def _stale_after(interval: str) -> int:
    return max(MIN_REFRESH_SECONDS, min(interval_seconds(interval), MAX_REFRESH_SECONDS))


def _age_seconds(updated_at: str, now: datetime) -> float | None:
    if not updated_at:
        return None
    try:
        stamp = datetime.fromisoformat(updated_at)
    except ValueError:
        return None
    stamp = stamp if stamp.tzinfo else stamp.replace(tzinfo=timezone.utc)
    return (now - stamp).total_seconds()


class IntradayService:
    """Reads intraday bars for the chart. Owns when to call the vendor and when not to."""

    def __init__(self, store: IntradayStore, *, splits_for=None, fetcher=None) -> None:
        self._store = store
        # How the lane learns the symbol's split basis. Injected so the service can be
        # tested without a price cache, and so the daily lane stays the single detector.
        self._splits_for = splits_for or (lambda symbol: [])
        # Injected rather than imported at the call site so the read path — freshness, split
        # invalidation, roll-up order, session filtering — is testable without a network.
        self._fetch = fetcher or fetch_grain

    def _fingerprint(self, symbol: str) -> str:
        try:
            return split_fingerprint(self._splits_for(symbol) or [])
        except Exception:
            logger.warning("market: %s split fingerprint unavailable", symbol, exc_info=True)
            return ""

    def series(
        self,
        symbol: str,
        interval: str,
        *,
        session: str = ALL_SESSIONS,
        days: int | None = None,
        refresh: bool = False,
        now: datetime | None = None,
    ) -> IntradaySeries:
        normalized = symbol.strip().upper()
        resolution = resolve(interval)
        grain = resolution.grain
        moment = now or datetime.now(timezone.utc)

        history = self._store.load(normalized, grain.key)
        fingerprint = self._fingerprint(normalized)
        age = _age_seconds(history.updated_at, moment) if history else None
        # A split rewrites the vendor's history, so a stale basis is refetched regardless of
        # how recently the cache was written.
        stale_basis = history is not None and history.split_fingerprint != fingerprint
        # `days` deeper than what is cached is a "load earlier" request, and only 1m can
        # answer one — every other grain already holds its whole window.
        wants_more = bool(days and history and grain.paged and _cached_days(history, moment) < days)
        needs_fetch = refresh or history is None or stale_basis or wants_more or (
            age is not None and age > _stale_after(interval)
        )

        result = None
        if needs_fetch:
            result = self._fetch(normalized, grain, days=days)
            if result.unavailable and history is None:
                return IntradaySeries(
                    symbol=normalized, interval=interval, session=session, bars=[],
                    grain=grain.key, window_days=grain.window_days,
                    unavailable=result.unavailable,
                )
            if result.bars:
                history = self._store.merge(normalized, grain.key, result.bars, split_fingerprint=fingerprint, now=moment)
            elif result.unavailable:
                # The vendor refused but the cache still holds real bars. Serve them and say
                # so, rather than blanking a chart the operator was already reading.
                result.warnings.append("Showing cached bars; the vendor refused a refresh.")

        stored = history.bars if history else []
        # FILTER THE SESSION FIRST, THEN ROLL UP. The order is not cosmetic once a bucket
        # spans the close: a 2h bucket anchored at 15:30 runs to 17:30, so rolling up first
        # would fold after-hours trade into a candle stamped 15:30, and the session filter
        # would then keep it — because its TIMESTAMP is regular. An operator who asked for
        # regular hours would be shown a high the session never reached. Filtering first
        # makes that bucket an honest 30-minute stub instead.
        scoped = filter_session(stored, session)
        bars = resample_intraday(scoped, interval_seconds(interval)) if resolution.derived else scoped

        return IntradaySeries(
            symbol=normalized, interval=interval, session=session, bars=bars,
            grain=grain.key, window_days=grain.window_days,
            fetched=bool(result and result.requests),
            requests=result.requests if result else 0,
            warnings=list(result.warnings) if result else [],
            unavailable=result.unavailable if result and not stored else None,
            updated_at=history.updated_at if history else "",
        )


def _cached_days(history, now: datetime) -> float:
    if not history.bars:
        return 0.0
    oldest = datetime.fromtimestamp(int(history.bars[0].t), tz=timezone.utc)
    return (now - oldest).total_seconds() / 86_400
