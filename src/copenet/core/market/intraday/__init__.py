"""Intraday bars: sub-day candles, fetched on demand and cached locally.

Its own lane, separate from the daily `PriceCache`, because the vendor's shape forces it —
short windows, per-request caps, revised bars, and a session dimension the daily lane has no
use for. See `docs/plans/INTRADAY_BARS.md` for the measured ceilings and the reasoning.
"""

from .intervals import GRAINS, GRAIN_BY_KEY, INTERVALS, Grain, Resolution, interval_seconds, offerable_intervals, resolve
from .service import IntradaySeries, IntradayService
from .resample import bucket_start, resample_intraday, session_anchor
from .store import ALL_SESSIONS, EXTENDED, REGULAR, IntradayHistory, IntradayStore, bar_session, filter_session, merge_bars

__all__ = [
    "ALL_SESSIONS", "EXTENDED", "GRAINS", "GRAIN_BY_KEY", "INTERVALS", "REGULAR",
    "Grain", "IntradayHistory", "IntradaySeries", "IntradayService", "IntradayStore", "Resolution",
    "bar_session", "bucket_start", "filter_session", "interval_seconds", "merge_bars",
    "offerable_intervals", "resample_intraday", "resolve", "session_anchor",
]
