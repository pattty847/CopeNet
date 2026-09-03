"""US-equity completed D/W/M candles with cache provenance and exchange-session gaps."""
from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache

from .models import MarketBar
from .price_history import bar_date, resample_bars, utc_midnight


@lru_cache(maxsize=8)
def _calendar(first_year: int, last_year: int):
    import exchange_calendars
    return exchange_calendars.get_calendar('XNYS', start=f'{first_year}-01-01', end=f'{last_year}-12-31')


@dataclass(frozen=True)
class CompletedCandles:
    bars: list[MarketBar]
    close_times: dict[int, str]
    status: str
    error: str | None = None


def completed_candles(history, timeframe: str, now: datetime) -> CompletedCandles:
    if not history.bars:
        return CompletedCandles([], {}, 'missing_history', 'No cached price history')
    fetched = datetime.fromisoformat(history.updated_at)
    if fetched.tzinfo is None or now.tzinfo is None:
        return CompletedCandles([], {}, 'missing_history', 'Cache completion provenance is unavailable')
    ordered = sorted(history.bars, key=lambda bar: bar.t)
    first = bar_date(ordered[0])
    start_date = first.replace(day=1) - timedelta(days=7)
    calendar = _calendar(start_date.year, now.year + 1)
    schedule = calendar.schedule.loc[start_date.isoformat(): (now.date() + timedelta(days=32)).isoformat()]
    groups: dict[object, list[tuple[object, datetime]]] = {}
    for session, row in schedule.iterrows():
        day = session.date()
        start = day if timeframe == 'daily' else day - timedelta(days=day.weekday()) if timeframe == 'weekly' else day.replace(day=1)
        close = row['close'].to_pydatetime().replace(tzinfo=timezone.utc)
        groups.setdefault(start, []).append((day, close))
    by_day = {bar_date(bar): bar for bar in ordered}
    selected, closes = [], {}
    partial_seed = None
    available = min(now, fetched)
    expected_latest = None
    for start, sessions in groups.items():
        if sessions[-1][0] < first:
            continue
        period_end = start if timeframe == 'daily' else start + timedelta(days=4) if timeframe == 'weekly' else start.replace(day=monthrange(start.year, start.month)[1])
        # Our schedule extends past now, so the last session is known even on holidays.
        end_close = sessions[-1][1]
        if sessions[-1][0] > period_end or end_close > now:
            continue
        expected_latest = utc_midnight(start)
        if end_close > available:
            continue
        # The chart includes its first IPO/cache-boundary partial bucket in indicator
        # warmup. Keep that identical historical seed, but never trigger on it itself.
        initial_partial = sessions[0][0] < first
        required = [(day, close) for day, close in sessions if day >= first]
        present = [by_day[day] for day, _ in required if day in by_day]
        if len(present) != len(required):
            return CompletedCandles([], {}, 'data_gap', 'Cached history is missing an exchange session; refresh this scan before evaluation')
        bars = resample_bars(present, timeframe)
        selected.extend(bars)
        closes[bars[-1].t] = end_close.isoformat()
        if initial_partial:
            partial_seed = bars[-1].t
    if not selected:
        return CompletedCandles([], {}, 'waiting_close', 'Waiting for a fully fetched completed candle')
    if selected[-1].t == partial_seed:
        return CompletedCandles(selected, closes, 'warming_up', 'The initial partial period is a chart warmup seed, not an eligible alert candle')
    if selected[-1].t != expected_latest:
        return CompletedCandles(selected, closes, 'stale', 'The latest completed candle has not been fetched after its close')
    return CompletedCandles(selected, closes, 'ready')
