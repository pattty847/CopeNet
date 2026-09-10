"""Fetch native-grain intraday bars from Yahoo, on a split-only basis.

Two things this does differently from the daily lane, both forced by the vendor:

- **`prepost=True`.** Yahoo returns the regular session only by default. Extended-hours
  candles are drawn on the chart (operator decision, see the plan), so they have to be
  requested. Their volume is structurally zero, which is the honest answer overnight and
  costs volume-weighted calculations nothing — a zero-volume bar contributes to neither side
  of a VWAP.
- **Paging.** `1m` is capped at 7 days per request but serves 30 days total, so full depth is
  several calls. No other grain is capped below its window.

Bars are split-only for the same reason the daily cache is: `auto_adjust=True` folds
dividends into the price as well, and a dividend retroactively shifts every prior price,
which drifts an append-only cache invisibly at the seam. `auto_adjust=False` asks Yahoo for
splits without dividends.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
import logging
import time as _time

from ..data_sources import yf_symbol
from ..fetch_pace import market_fetch_pace
from ..models import MarketBar
from .intervals import Grain

logger = logging.getLogger(__name__)


@dataclass
class FetchResult:
    """Bars plus what happened getting them. Warnings are surfaced, never swallowed: a
    partial fetch that looks like a complete one is how a chart quietly loses a week."""

    bars: list[MarketBar]
    requests: int = 0
    warnings: list[str] = field(default_factory=list)
    #: Set when the vendor refused outright — its message carries the real ceiling.
    unavailable: str | None = None


def _windows(grain: Grain, days: int, today: date) -> list[tuple[date, date]]:
    """Split a request into vendor-legal spans, newest first.

    Newest first matters: a paged fetch that is interrupted or rate-limited should leave the
    operator with recent history rather than a gap ending three weeks ago.
    """
    span = min(days, grain.window_days)
    out: list[tuple[date, date]] = []
    end = today + timedelta(days=1)  # `end` is exclusive on Yahoo
    remaining = span
    while remaining > 0:
        chunk = min(grain.request_days, remaining)
        start = end - timedelta(days=chunk)
        out.append((start, end))
        end = start
        remaining -= chunk
    return out


def _frame_to_bars(frame) -> list[MarketBar]:
    """Yahoo hands back an exchange-local tz-aware index for intraday. Keep the instant and
    convert to unix seconds — unlike the daily lane, the time of day IS the information."""
    import pandas as pd

    if frame is None or frame.empty:
        return []
    frame = frame.reset_index()
    frame.columns = [str(column).lower() for column in frame.columns]
    stamp_column = next((name for name in ("datetime", "date", "index") if name in frame), None)
    if stamp_column is None or "close" not in frame:
        return []
    frame = frame.dropna(subset=[stamp_column, "close"])
    bars: list[MarketBar] = []
    for _, row in frame.iterrows():
        stamp = pd.Timestamp(row[stamp_column])
        if stamp is pd.NaT:
            continue
        moment = stamp.tz_localize(timezone.utc) if stamp.tzinfo is None else stamp
        volume = row.get("volume")
        bars.append(MarketBar(
            t=int(moment.timestamp()),
            o=float(row["open"]), h=float(row["high"]), l=float(row["low"]), c=float(row["close"]),
            # Overnight bars report no volume. Zero is the measurement, not a gap to fill.
            v=int(volume) if volume == volume and volume is not None else 0,
        ))
    return bars


def fetch_grain(
    symbol: str,
    grain: Grain,
    *,
    days: int | None = None,
    today: date | None = None,
    sleep=_time.sleep,
) -> FetchResult:
    """Pull `days` of one native grain, paging when the vendor caps the request span."""
    try:
        import yfinance as yf
    except ImportError as exc:  # pragma: no cover - dependency exists in packaged env
        raise RuntimeError("yfinance is required for market data") from exc

    requested = grain.window_days if days is None else max(1, min(int(days), grain.window_days))
    windows = _windows(grain, requested, today or datetime.now(timezone.utc).date())
    result = FetchResult(bars=[])
    ticker = yf.Ticker(yf_symbol(symbol))
    pace = market_fetch_pace()

    by_time: dict[int, MarketBar] = {}
    for index, (start, end) in enumerate(windows):
        if index:
            sleep(pace)
        try:
            frame = ticker.history(
                start=start, end=end, interval=grain.key,
                auto_adjust=False, prepost=True, actions=False,
            )
        except Exception as exc:
            message = str(exc)
            logger.warning("market: %s %s window %s..%s failed: %s", symbol, grain.key, start, end, message)
            # A refusal on the FIRST window is the vendor saying the grain is unavailable.
            # A refusal on a later one only means history ran out before the window did.
            if index == 0:
                result.unavailable = message
                return result
            result.warnings.append(f"{grain.key} history stops before {end}: {message}")
            break
        result.requests += 1
        page = _frame_to_bars(frame)
        if not page and index:
            # Older windows legitimately run dry; stop paging rather than burn requests.
            break
        # Later windows are OLDER, so earlier pages win on collision — the vendor revises
        # recent bars, and the newest response is the current truth.
        for bar in page:
            by_time.setdefault(int(bar.t), bar)

    result.bars = [by_time[key] for key in sorted(by_time)]
    return result
