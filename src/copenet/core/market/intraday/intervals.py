"""The interval algebra: which grains CopeNet fetches, and what it derives from them.

Three facts about the vendor shape this module, all measured (see `docs/plans/INTRADAY_BARS.md`):

1. `15m` and `30m` are strictly worse than `5m` on Yahoo — the same 60-day ceiling, fewer
   bars. Fetching them buys nothing that resampling `5m` does not already give.
2. `1m` is the only interval capped per request (7 days) below its total window (30 days).
3. Yahoo anchors hourly bars to the session open (09:30, 10:30 … 15:30), not the wall clock.

So CopeNet fetches three NATIVE grains and derives everything else, which is the same shape
the daily cache already has: store daily, derive weekly and monthly.
"""

from __future__ import annotations

from dataclasses import dataclass

MINUTE = 60


@dataclass(frozen=True)
class Grain:
    """An interval CopeNet actually requests from the vendor."""

    key: str
    seconds: int
    #: Total history the vendor will serve, in calendar days.
    window_days: int
    #: Largest span one request may ask for. Equal to `window_days` unless the vendor caps it.
    request_days: int

    @property
    def paged(self) -> bool:
        return self.request_days < self.window_days


#: Ordered coarsest-last. `5m` is fetched despite being derivable from `1m` because it reaches
#: 60 days where `1m` reaches 30 — depth, not resolution, is why it earns a request.
GRAINS: tuple[Grain, ...] = (
    Grain("1m", 1 * MINUTE, window_days=30, request_days=7),
    Grain("5m", 5 * MINUTE, window_days=60, request_days=60),
    Grain("1h", 60 * MINUTE, window_days=730, request_days=730),
)

GRAIN_BY_KEY = {grain.key: grain for grain in GRAINS}

#: Every interval the chart may ask for, in seconds. A value is offerable only if some grain
#: divides it exactly — see `resolve`. `7m` is deliberately absent: offering it and silently
#: rounding to 5m would be worse than not offering it.
INTERVALS: tuple[str, ...] = (
    "1m", "2m", "3m", "5m", "10m", "15m", "20m", "30m", "1h", "2h", "4h",
)

_SECONDS_BY_INTERVAL: dict[str, int] = {
    "1m": 1 * MINUTE, "2m": 2 * MINUTE, "3m": 3 * MINUTE, "5m": 5 * MINUTE,
    "10m": 10 * MINUTE, "15m": 15 * MINUTE, "20m": 20 * MINUTE, "30m": 30 * MINUTE,
    "1h": 60 * MINUTE, "2h": 120 * MINUTE, "4h": 240 * MINUTE,
}


def interval_seconds(interval: str) -> int:
    try:
        return _SECONDS_BY_INTERVAL[interval]
    except KeyError:
        raise ValueError(f"unknown intraday interval: {interval!r}") from None


@dataclass(frozen=True)
class Resolution:
    """How one requested interval is served: which grain to fetch, and whether to roll it up."""

    interval: str
    grain: Grain
    #: True when the grain has to be bucketed rather than returned as-is.
    derived: bool

    @property
    def window_days(self) -> int:
        return self.grain.window_days


def resolve(interval: str) -> Resolution:
    """Pick the grain that serves `interval`.

    Two rules, and the second is the one worth stating: prefer the COARSEST grain that
    divides the interval exactly, because coarser grains reach further back. A 15m chart can
    be built from `1m` or `5m` and the candles are identical either way — but `5m` reaches 60
    days where `1m` reaches 30, so choosing `1m` would halve the available history for no
    gain at all.
    """
    seconds = interval_seconds(interval)
    for grain in reversed(GRAINS):
        if seconds % grain.seconds == 0:
            return Resolution(interval=interval, grain=grain, derived=seconds != grain.seconds)
    raise ValueError(f"no native grain divides {interval!r}")


def offerable_intervals() -> tuple[str, ...]:
    """Intervals a selector may show. Everything in `INTERVALS` resolves by construction;
    this asserts it rather than trusting the two lists to stay in agreement."""
    return tuple(interval for interval in INTERVALS if _divides_some_grain(interval))


def _divides_some_grain(interval: str) -> bool:
    seconds = interval_seconds(interval)
    return any(seconds % grain.seconds == 0 for grain in GRAINS)
