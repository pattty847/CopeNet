"""Provenance for a currently forming exchange period, from cached daily bars only."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .alert_candles import _calendar
from .models import MarketBar
from .price_history import bar_date, resample_bars, utc_midnight


@dataclass(frozen=True)
class FormingCandle:
    bar: MarketBar | None
    close_at: str | None
    error: str | None = None


def forming_candle(history, timeframe, now):
    fetched = datetime.fromisoformat(history.updated_at)
    day = now.astimezone(ZoneInfo('America/New_York')).date()
    start = day if timeframe == 'daily' else day - timedelta(days=day.weekday()) if timeframe == 'weekly' else day.replace(day=1)
    end = start + timedelta(days=1 if timeframe == 'daily' else 7 if timeframe == 'weekly' else 32)
    schedule = _calendar(start.year - 1, end.year + 1).schedule.loc[start.isoformat():end.isoformat()]
    sessions = []
    for session, row in schedule.iterrows():
        session_day = session.date()
        if timeframe == 'daily' and session_day != start:
            continue
        if timeframe == 'weekly' and session_day >= start + timedelta(days=7):
            continue
        if timeframe == 'monthly' and session_day.month != start.month:
            continue
        sessions.append((session_day, row['open'].to_pydatetime().replace(tzinfo=timezone.utc), row['close'].to_pydatetime().replace(tzinfo=timezone.utc)))
    if not sessions or now < sessions[0][1] or now >= sessions[-1][2]:
        return FormingCandle(None, None)
    close_at = sessions[-1][2].isoformat()
    # A previous day's cached tail is never an observation of today's interaction.
    eligible = [(d, opened, closed) for d, opened, closed in sessions if opened <= now]
    if not eligible:
        return FormingCandle(None, close_at)
    observed_day = eligible[-1][0]
    if fetched.astimezone(ZoneInfo('America/New_York')).date() < observed_day:
        return FormingCandle(None, close_at, 'Waiting for the linked scan to refresh this period')
    by_day = {bar_date(bar): bar for bar in history.bars}
    if any(d not in by_day for d, _, _ in eligible):
        return FormingCandle(None, close_at, 'Cached forming period is missing an exchange session')
    if fetched < eligible[-1][1]:
        return FormingCandle(None, close_at, 'Waiting for a scan after the session opens')
    bars = [by_day[d] for d, _, _ in eligible]
    period = resample_bars(bars, timeframe)[0]
    assert period.t == utc_midnight(start)
    return FormingCandle(period, close_at)
