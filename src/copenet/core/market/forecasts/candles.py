"""Calendar eligibility and publication-basis candles for forward forecasts, without I/O."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math

from ..alert_candles import _calendar
from ..price_history import bar_date, split_fingerprint


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


@dataclass(frozen=True)
class ForecastCandles:
    bars: list[dict]
    sessions: list[dict]
    endpoints: dict[str, dict]
    health: str
    reason: str | None
    source: dict


def forecast_candles(forecast: dict, history, now: datetime) -> ForecastCandles:
    published = datetime.fromisoformat(forecast['publishedAt'])
    provenance = forecast['provenance']
    source = {'symbol': history.symbol, 'fetchedAt': history.updated_at,
              'splitFingerprint': split_fingerprint(history.splits), 'splits': history.splits,
              'calendar': provenance.get('calendar'), 'basis': provenance.get('basis')}

    def blocked(health, reason):
        return ForecastCandles([], [], {}, health, reason, source)

    if provenance.get('basis') != 'split_adjusted' or provenance.get('calendar') != 'XNYS':
        return blocked('unsupported', 'Forecast requires split-only US exchange-session provenance')
    if history.symbol != forecast['instrument']['symbol']:
        return blocked('unsupported', 'Price history does not belong to the forecast instrument')
    original = provenance.get('splits')
    if original is None or provenance.get('splitFingerprint') != split_fingerprint(original):
        return blocked('revision_review', 'Publication split provenance is missing or inconsistent')
    current = dict(history.splits)
    if len(current) != len(history.splits) or any(current.get(day) != ratio for day, ratio in original):
        return blocked('revision_review', 'Recorded split history changed or disappeared')
    new_splits = [(day, ratio) for day, ratio in history.splits if day not in dict(original)]
    if any(day <= published.date().isoformat() or day > now.date().isoformat() or not math.isfinite(ratio) or ratio <= 0 for day, ratio in new_splits):
        return blocked('revision_review', 'New split history contradicts the publication basis')
    factor = math.prod(ratio for _, ratio in new_splits)
    source['publicationBasisFactor'] = factor
    fetched = datetime.fromisoformat(history.updated_at)
    if now.tzinfo is None or published.tzinfo is None or fetched.tzinfo is None:
        return blocked('stale', 'Timestamp completion provenance requires a timezone')
    deadline = published + timedelta(days=56)
    calendar = _calendar(published.year - 1, deadline.year + 1)
    schedule = calendar.schedule.loc[(published.date() - timedelta(days=10)).isoformat(): deadline.date().isoformat()]
    all_sessions = []
    for day, row in schedule.iterrows():
        opened = row['open'].to_pydatetime().replace(tzinfo=timezone.utc)
        closed = row['close'].to_pydatetime().replace(tzinfo=timezone.utc)
        all_sessions.append({'date': day.date().isoformat(), 'open': opened.isoformat(), 'close': closed.isoformat()})
    endpoints = {}
    for days in (28, 56):
        due = published + timedelta(days=days)
        endpoint = next(session for session in reversed(all_sessions) if datetime.fromisoformat(session['close']) <= due)
        endpoints[str(days // 7) + 'w'] = {**endpoint, 'dueAt': due.isoformat()}
    sessions = [session for session in all_sessions if datetime.fromisoformat(session['open']) > published
                and datetime.fromisoformat(session['close']) <= deadline]
    by_day = {}
    for bar in history.bars:
        day = bar_date(bar).isoformat()
        raw = asdict(bar)
        if day in by_day and raw != by_day[day]:
            return blocked('revision_review', 'Conflicting duplicate daily bars require source review')
        by_day[day] = raw
    bars, health, reason = [], 'ready', None
    for session in sessions:
        close = datetime.fromisoformat(session['close'])
        if close > now:
            break
        if close > fetched:
            health, reason = 'stale', f"The completed {session['date']} session has not been fetched after its close"
            break
        raw = by_day.get(session['date'])
        if raw is None:
            health, reason = 'data_gap', f"Missing required session {session['date']}; later bars are not evaluated"
            break
        normalized = {**raw, **{key: raw[key] * factor for key in ('o', 'h', 'l', 'c')},
                      'date': session['date'], 'sessionClose': session['close']}
        bars.append(normalized)
    return ForecastCandles(bars, sessions, endpoints, health, reason, source)


def history_revision(previous: list[dict], current: list[dict]) -> bool:
    """Tolerance only accommodates arithmetic reversing a later split; gaps block scoring."""
    by_day = {bar['date']: bar for bar in current}
    for old in previous:
        new = by_day.get(old['date'])
        if new is None:
            return True
        if old['v'] != new['v'] or any(not math.isclose(old[key], new[key], rel_tol=1e-10, abs_tol=1e-10)
                                      for key in ('o', 'h', 'l', 'c')):
            return True
    return False
