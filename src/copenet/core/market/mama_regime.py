"""MAMA/FAMA regime, computed by the same Ehlers implementation the chart draws.

There is exactly one MAMA in CopeNet and it lives in the indicator registry
(`indicators/calc/ehlers.ts`). This module reaches it through the bundled evaluator
instead of reimplementing it in pandas.

That is not ceremony. Until 2026-09-05 this value came from a 10/21 EWMA crossover
labelled "MAMA above FAMA" — no Hilbert transform, no adaptive alpha — and it went to
the model in every fact packet under that name. The registry's own header warns about
exactly this failure: a degraded MAMA "still looks entirely plausible on a chart". A
second implementation is how the label and the math came apart, so there is not going
to be a second implementation.

When the evaluator is unavailable the regime says so. It never falls back to an
approximation, because an approximation wearing this name is the original bug.
"""

from __future__ import annotations

import pandas as pd

from .alert_evaluator import evaluator_request

ABOVE = "MAMA above FAMA"
BELOW = "MAMA below FAMA"
WARMING_UP = "warming up"
UNAVAILABLE = "unavailable (indicator evaluator not built)"

# The chart's own default settling region for MAMA. Stated here only so callers can size
# history; the authoritative value is the registry's `warmup` input and the evaluator
# returns nulls across it regardless of what this constant says.
SETTLING_BARS = 32

_OPERAND = {"kind": "indicator", "indicatorId": "mama", "config": {}}


def _bars_payload(frame: pd.DataFrame) -> list[dict[str, float]]:
    """Strictly ordered, fully finite OHLCV rows — the only shape the evaluator accepts."""
    if frame is None or frame.empty:
        return []
    columns = {str(column).lower(): column for column in frame.columns}
    date_column = columns.get("date") or columns.get("datetime")
    if date_column is None or not {"open", "high", "low", "close"} <= set(columns):
        return []
    # Divide by a Timedelta, never by a hardcoded 10**9. Datetime resolution here is not
    # fixed — pandas hands back datetime64[s] or [ns] depending on how the column was built
    # — so a nanosecond constant silently returns 0 for every second-resolution frame, and
    # the ordering guard below then discards all but the first bar.
    times = pd.to_datetime(frame[date_column], errors="coerce", utc=True)
    epoch = pd.Timestamp("1970-01-01", tz="UTC")
    frame = frame.assign(_t=((times - epoch) // pd.Timedelta("1s")))
    rows: list[dict[str, float]] = []
    previous = None
    for _, row in frame.iterrows():
        try:
            bar = {
                "t": int(row["_t"]),
                "o": float(row[columns["open"]]),
                "h": float(row[columns["high"]]),
                "l": float(row[columns["low"]]),
                "c": float(row[columns["close"]]),
                "v": float(row[columns["volume"]]) if "volume" in columns else 0.0,
            }
        except (TypeError, ValueError):
            continue
        if any(value != value or value in (float("inf"), float("-inf")) for value in bar.values()):
            continue
        # A repeated or out-of-order timestamp is rejected by the evaluator outright, which
        # would cost the whole symbol its regime. Drop the offending row instead.
        if previous is not None and bar["t"] <= previous:
            continue
        previous = bar["t"]
        rows.append(bar)
    return rows


def mama_regime(frame: pd.DataFrame, *, timeframe: str = "weekly") -> str:
    """Return the MAMA/FAMA state for the final bar of ``frame``.

    Never raises: an unbuilt evaluator, a missing Node, or a frame the evaluator refuses
    all resolve to a string the caller can display and the model can read as absent.
    """
    bars = _bars_payload(frame)
    if len(bars) < 2:
        return WARMING_UP
    try:
        response = evaluator_request(
            {
                "action": "evaluate",
                "timeframe": timeframe,
                "bars": bars,
                "left": {**_OPERAND, "output": "mama"},
                "right": {**_OPERAND, "output": "fama"},
            }
        )
    except ValueError:
        return UNAVAILABLE
    latest = (response.get("points") or [{}])[-1]
    mama, fama = latest.get("left"), latest.get("right")
    if mama is None or fama is None:
        return WARMING_UP
    return ABOVE if mama >= fama else BELOW
