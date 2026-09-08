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

import json

import pandas as pd

from .alert_evaluator import evaluator_request

ABOVE = "MAMA above FAMA"
BELOW = "MAMA below FAMA"
WARMING_UP = "warming up"
UNAVAILABLE = "unavailable (indicator evaluator not built)"
UNREADABLE = "unreadable history"

# The evaluator refuses payloads over 8 MB. Weekly history is unbounded by CHART_BAR_LIMITS —
# a long-listed symbol carries ~2,400 bars, ~170 KB of JSON — so a universe sweep has to be
# chunked, not merely batched. Half the ceiling leaves room for the Node heap the bundle runs
# under. Sending a shorter window instead is not an option: these are recursive filters whose
# value depends on their seed, so a truncated window would disagree with the chart.
_CHUNK_BUDGET_BYTES = 4_000_000
_MAX_SYMBOLS_PER_CHUNK = 1000

# The chart's own default settling region for MAMA. Stated here only so callers can size
# history; the authoritative value is the registry's `warmup` input and the evaluator
# returns nulls across it regardless of what this constant says.
SETTLING_BARS = 32

_MAMA_SPEC = {"indicatorId": "mama", "config": {}}


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


def _state(values: dict) -> str:
    reading = (values or {}).get("mama") or {}
    mama, fama = reading.get("mama"), reading.get("fama")
    if mama is None or fama is None:
        return WARMING_UP
    return ABOVE if mama >= fama else BELOW


def _chunks(payloads: list[tuple[str, list[dict[str, float]]]]) -> list[list[dict]]:
    """Group symbol payloads into evaluator requests that fit the input ceiling."""
    chunks: list[list[dict]] = []
    current: list[dict] = []
    size = 0
    for key, bars in payloads:
        request = {"key": key, "bars": bars, "indicators": [_MAMA_SPEC]}
        cost = len(json.dumps(request, allow_nan=False))
        if current and (size + cost > _CHUNK_BUDGET_BYTES or len(current) >= _MAX_SYMBOLS_PER_CHUNK):
            chunks.append(current)
            current, size = [], 0
        current.append(request)
        size += cost
    if current:
        chunks.append(current)
    return chunks


def mama_regimes(frames: dict[str, pd.DataFrame], *, timeframe: str = "weekly") -> dict[str, str]:
    """MAMA/FAMA state for many symbols, in as few Node processes as the ceiling allows.

    Spawning the evaluator costs roughly 80ms before it computes anything, which is fine for
    one ticker and is the whole cost of a universe sweep. Batching turns a per-symbol spawn
    into a handful of them.

    Never raises. A chunk the evaluator cannot run reports UNAVAILABLE for its symbols; a
    single symbol the evaluator rejects reports UNREADABLE for itself alone, so one bad frame
    cannot quietly remove names from a count computed over this result.
    """
    payloads = [(key, _bars_payload(frame)) for key, frame in frames.items()]
    states = {key: WARMING_UP for key, bars in payloads if len(bars) < 2}
    runnable = [(key, bars) for key, bars in payloads if len(bars) >= 2]

    for chunk in _chunks(runnable):
        try:
            response = evaluator_request({"action": "latest", "timeframe": timeframe, "requests": chunk})
        except ValueError:
            states.update({request["key"]: UNAVAILABLE for request in chunk})
            continue
        returned = {str(row.get("key")): row for row in response.get("results") or []}
        for request in chunk:
            row = returned.get(request["key"])
            if row is None or row.get("error"):
                states[request["key"]] = UNREADABLE
            else:
                states[request["key"]] = _state(row.get("values") or {})
    return states


def mama_regime(frame: pd.DataFrame, *, timeframe: str = "weekly") -> str:
    """MAMA/FAMA state for the final bar of ``frame``.

    A batch of one, deliberately: one code path means a symbol cannot read differently
    on the ticker page than it does in the sweep.
    """
    return mama_regimes({"symbol": frame}, timeframe=timeframe)["symbol"]
