"""Pure transforms over daily price history: resampling, dividend adjustment, merging.

Split out from `price_cache.py` so every rule here is testable without a network call or
a filesystem. Nothing in this module does I/O.

The stored basis is split-only. Splits are mechanical — a 4-for-1 turns one share into
four, so an unadjusted history shows a 75% "crash" that never happened. Dividends are
not mechanical: adjusting for them converts a price chart into a total-return chart,
which answers "what did I earn holding this" rather than "what did this cost". Only the
second question is the one a price chart or a P/E ratio is asking, so dividends stay out
of the stored bars and are applied here on demand.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from .models import MarketBar


SPLIT_ADJUSTED = "split_adjusted"
TOTAL_RETURN = "total_return"
PRICE_BASES = (SPLIT_ADJUSTED, TOTAL_RETURN)

DAILY = "daily"
WEEKLY = "weekly"
MONTHLY = "monthly"
TIMEFRAMES = (DAILY, WEEKLY, MONTHLY)

# Chart transport and background indicators must share their recursive-calculation prefix.
# W/M stay unbounded so financial overlays retain their earliest historical anchors.
CHART_BAR_LIMITS: dict[str, int | None] = {DAILY: 2_600, WEEKLY: None, MONTHLY: None}


def chart_history_window(bars: list[MarketBar], timeframe: str) -> list[MarketBar]:
    limit = CHART_BAR_LIMITS[timeframe]
    return bars[-limit:] if limit else list(bars)


def bar_date(bar: MarketBar) -> date:
    """The UTC calendar date a bar belongs to."""
    return datetime.fromtimestamp(int(bar.t), tz=timezone.utc).date()


def utc_midnight(day: date) -> int:
    """Unix seconds at UTC midnight — the timestamp convention every bar uses."""
    return int(datetime(day.year, day.month, day.day, tzinfo=timezone.utc).timestamp())


def daily_close_available_at(bar: MarketBar) -> datetime:
    """Conservative US-equity daily-close availability, not the UTC session label.

    Early-close sessions deliberately wait until 16:00 New York. The caller must also
    establish that the cached bar was fetched after this moment, not just that time passed.
    """
    return datetime.combine(bar_date(bar), time(16), ZoneInfo("America/New_York"))


def split_fingerprint(splits: list[tuple[str, float]]) -> str:
    """Stable identity for a split history.

    A change here means every stored price is on a stale basis and the symbol must be
    rebuilt from scratch — Yahoo's `close` is already split-adjusted on their side, so a
    new split silently rewrites all of their history for that symbol.
    """
    return "|".join(f"{day}:{ratio:g}" for day, ratio in sorted(splits))


def merge_daily_bars(
    existing: list[MarketBar],
    incoming: list[MarketBar],
) -> list[MarketBar]:
    """Overwrite by timestamp, never append blindly.

    The newest bar is provisional: during market hours Yahoo returns today's partial bar
    with the last trade as `close` and volume-so-far. Re-fetching the tail and letting
    incoming win is what keeps the current candle live.
    """
    by_time: dict[int, MarketBar] = {int(bar.t): bar for bar in existing}
    by_time.update({int(bar.t): bar for bar in incoming})
    return [by_time[key] for key in sorted(by_time)]


def merge_actions(
    existing: list[tuple[str, float]],
    incoming: list[tuple[str, float]],
) -> list[tuple[str, float]]:
    """Merge split or dividend events, keyed by date, oldest first."""
    by_day: dict[str, float] = {str(day): float(value) for day, value in existing}
    by_day.update({str(day): float(value) for day, value in incoming})
    return sorted(by_day.items())


def _period_start(day: date, timeframe: str) -> date:
    if timeframe == WEEKLY:
        return day - timedelta(days=day.weekday())
    if timeframe == MONTHLY:
        return day.replace(day=1)
    return day


def resample_bars(daily: list[MarketBar], timeframe: str) -> list[MarketBar]:
    """Roll daily bars up to weekly or monthly.

    Anchored to the Monday of the week and the first of the month rather than the first
    *trading* day, which is Yahoo's own convention. Holding to it matters because
    financial overlays snap to candle timestamps: if our weekly bars landed on a Tuesday
    after a Monday holiday, every overlay point in that week would inject a new slot into
    the chart's index-based time axis instead of sitting on an existing candle.
    """
    if timeframe not in TIMEFRAMES:
        raise ValueError(f"timeframe must be one of {TIMEFRAMES}: {timeframe!r}")
    if timeframe == DAILY or not daily:
        return list(daily)
    grouped: dict[date, list[MarketBar]] = {}
    for bar in sorted(daily, key=lambda row: int(row.t)):
        grouped.setdefault(_period_start(bar_date(bar), timeframe), []).append(bar)
    return [
        MarketBar(
            t=utc_midnight(start),
            o=group[0].o,
            h=max(row.h for row in group),
            l=min(row.l for row in group),
            c=group[-1].c,
            v=sum(int(row.v) for row in group),
        )
        for start, group in sorted(grouped.items())
    ]


def apply_dividend_adjustment(
    daily: list[MarketBar],
    dividends: list[tuple[str, float]],
) -> list[MarketBar]:
    """Back-adjust split-only bars onto a total-return basis.

    Standard back-adjustment: a dividend with ex-date D scales every bar *before* D by
    `1 - dividend / previous close`, and those factors compound going backwards. Bars on
    or after the ex-date are untouched, which is why the most recent price is identical
    on both bases and the two only diverge as you look further back.

    Volume is a share count, not a price, so it is never scaled.
    """
    if not daily or not dividends:
        return list(daily)
    ordered = sorted(daily, key=lambda row: int(row.t))
    amount_by_day = {str(day): float(amount) for day, amount in dividends if float(amount) > 0}
    factors = [1.0] * len(ordered)
    running = 1.0
    for index in range(len(ordered) - 1, -1, -1):
        factors[index] = running
        amount = amount_by_day.get(bar_date(ordered[index]).isoformat())
        if amount is None or index == 0:
            continue
        previous_close = float(ordered[index - 1].c)
        if previous_close > 0:
            running *= max(0.0, 1.0 - amount / previous_close)
    return [
        MarketBar(
            t=int(bar.t),
            o=round(bar.o * factor, 4),
            h=round(bar.h * factor, 4),
            l=round(bar.l * factor, 4),
            c=round(bar.c * factor, 4),
            v=int(bar.v),
        )
        for bar, factor in zip(ordered, factors)
    ]


def derive_bars(
    daily: list[MarketBar],
    dividends: list[tuple[str, float]],
    *,
    timeframe: str = DAILY,
    basis: str = SPLIT_ADJUSTED,
) -> list[MarketBar]:
    """Stored split-only dailies to whatever basis and timeframe a consumer asked for.

    Dividends are applied before resampling so a weekly bar's open/high/low/close all sit
    on the same factor as the days that produced them.
    """
    if basis not in PRICE_BASES:
        raise ValueError(f"basis must be one of {PRICE_BASES}: {basis!r}")
    adjusted = (
        apply_dividend_adjustment(daily, dividends) if basis == TOTAL_RETURN else list(daily)
    )
    return resample_bars(adjusted, timeframe)
