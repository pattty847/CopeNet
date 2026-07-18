"""Slope-aware 5-state weekly trend classifier — Signal Engine v2, inch #1.

Replaces the binary up/down trend call with five semantic states:

    STRONG_UP > UP > TRANSITION > DOWN > STRONG_DOWN

Design rules (agreed 2026-07-18, signal-engine-v2 thread):
- PURE function of the supplied weekly frame (same point-in-time discipline as features.py):
  a frame sliced to `as_of` makes lookahead structurally impossible.
- Slope-aware: price above a FALLING 40-week average is TRANSITION, not "up". This kills the
  old `last > close.iloc[0]` permissiveness that inflated breadth (and regime) downstream.
- Normalized, not absolute: slopes and distances are measured in ATR units so one rule fits
  KO and NVDA alike (distribution-relative over hand-picked percents).
- Chop resistance lives in the STATE MACHINE, not a fancier filter: dead zones, entry/exit
  hysteresis, and a 2-week persistence gate for STRONG states.
- Constants are PRE-REGISTERED (seeded by eye, sanity-checked by replay's state distribution —
  never tuned to maximize a backtest).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum

import pandas as pd

TREND_STATE_VERSION = "v1"

# Pre-registered constants (see module docstring — replay validates, it does not tune).
SLOPE_DEAD_ZONE_ATR = 0.25   # |5-week MA40 change| below this many ATR14 = "flat" slope
DIST_NEUTRAL_ATR = 0.5       # |close - MA40| below this many ATR14 = "at" the anchor
STRONG_PERSISTENCE_WEEKS = 2  # consecutive weeks of full-stack condition to enter a STRONG state
MIN_HISTORY_WEEKS = 46       # MA40 needs 40 bars, its 5-week slope needs 5 more


class TrendState(str, Enum):
    STRONG_UP = "strong_up"
    UP = "up"
    TRANSITION = "transition"
    DOWN = "down"
    STRONG_DOWN = "strong_down"


@dataclass(frozen=True)
class TrendSnapshot:
    """Latest trend state plus the normalized ingredients that produced it."""

    symbol: str
    as_of: str | None
    state: str | None            # None when history is too thin to classify
    prior_state: str | None      # state immediately before the current run
    weeks_in_state: int          # length of the current consecutive run
    entered_at: str | None       # date the current run started (ISO)
    slope40_atr: float | None    # 5-week MA40 change, in ATR14 units
    slope10_atr: float | None    # 5-week MA10 change, in ATR14 units
    dist40_atr: float | None     # (close - MA40) / ATR14
    thin_history: bool

    def to_dict(self) -> dict:
        return asdict(self)


def _normalize(frame: pd.DataFrame) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])
    cols = {str(c).lower(): c for c in frame.columns}
    out = pd.DataFrame()
    date_col = cols.get("date") or cols.get("datetime")
    dates = pd.to_datetime(frame[date_col]) if date_col else pd.to_datetime(frame.index)
    if getattr(dates.dt, "tz", None) is not None:
        dates = dates.dt.tz_localize(None)
    out["date"] = dates
    for name in ("high", "low", "close"):
        out[name] = pd.to_numeric(frame[cols[name]], errors="coerce") if name in cols else float("nan")
    out = out.dropna(subset=["close"]).sort_values("date").reset_index(drop=True)
    # ATR needs high/low; fall back to close so close-only frames still classify
    out["high"] = out["high"].fillna(out["close"])
    out["low"] = out["low"].fillna(out["close"])
    return out


def _atr(frame: pd.DataFrame, period: int = 14) -> pd.Series:
    high, low, close = frame["high"], frame["low"], frame["close"]
    prev_close = close.shift(1)
    tr = pd.concat([(high - low), (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    return tr.rolling(period, min_periods=period).mean()


def classify_trend_series(frame: pd.DataFrame) -> pd.DataFrame:
    """Run the state machine over the whole weekly frame.

    Returns a DataFrame with one row per classifiable bar: date, state, and the normalized
    ingredients. Every ingredient is a trailing computation and the machine only looks
    backward, so the state at bar t is identical whether computed from the full series or
    from a slice ending at t (slice independence — tested).
    """
    f = _normalize(frame)
    empty = pd.DataFrame(columns=["date", "state", "slope40_atr", "slope10_atr", "dist40_atr"])
    if len(f) < MIN_HISTORY_WEEKS:
        return empty

    close = f["close"].astype(float)
    ma10 = close.rolling(10, min_periods=10).mean()
    ma30 = close.rolling(30, min_periods=30).mean()
    ma40 = close.rolling(40, min_periods=40).mean()
    atr = _atr(f).replace(0, float("nan"))

    slope40 = (ma40 - ma40.shift(5)) / atr
    slope10 = (ma10 - ma10.shift(5)) / atr
    dist40 = (close - ma40) / atr

    stack_up = (close > ma10) & (ma10 > ma30) & (ma30 > ma40)
    stack_down = (close < ma10) & (ma10 < ma30) & (ma30 < ma40)

    # Raw per-bar candidate conditions (no memory yet)
    strong_up_raw = stack_up & (slope40 > SLOPE_DEAD_ZONE_ATR) & (slope10 > 0)
    strong_down_raw = stack_down & (slope40 < -SLOPE_DEAD_ZONE_ATR) & (slope10 < 0)
    # Plain UP/DOWN entry requires the anchor itself to be MOVING (slope beyond the dead zone):
    # price hovering above a flat MA40 is a pause, not a trend. The hold branches below let an
    # established trend ride through a flattening anchor without churning out.
    up_raw = (dist40 > DIST_NEUTRAL_ATR) & (slope40 > SLOPE_DEAD_ZONE_ATR)
    down_raw = (dist40 < -DIST_NEUTRAL_ATR) & (slope40 < -SLOPE_DEAD_ZONE_ATR)

    valid = slope40.notna() & dist40.notna()
    first = int(valid.idxmax()) if valid.any() else -1
    if first < 0:
        return empty

    states: list[str] = []
    dates: list[pd.Timestamp] = []
    prev: str | None = None
    strong_up_streak = 0
    strong_down_streak = 0
    for i in range(first, len(f)):
        if not bool(valid.iloc[i]):
            # ATR gap mid-series (flat/no-range stretch) — hold the prior state
            states.append(prev or TrendState.TRANSITION.value)
            dates.append(f["date"].iloc[i])
            continue
        su, sd = bool(strong_up_raw.iloc[i]), bool(strong_down_raw.iloc[i])
        strong_up_streak = strong_up_streak + 1 if su else 0
        strong_down_streak = strong_down_streak + 1 if sd else 0
        c, m10 = float(close.iloc[i]), float(ma10.iloc[i])
        d40, s40 = float(dist40.iloc[i]), float(slope40.iloc[i])

        # 1. STRONG hysteresis: once in a strong state, hold it until price loses/reclaims MA10.
        if prev == TrendState.STRONG_UP.value and c > m10 and not sd:
            state = TrendState.STRONG_UP.value
        elif prev == TrendState.STRONG_DOWN.value and c < m10 and not su:
            state = TrendState.STRONG_DOWN.value
        # 2. STRONG entry: full-stack condition held STRONG_PERSISTENCE_WEEKS in a row.
        elif strong_up_streak >= STRONG_PERSISTENCE_WEEKS:
            state = TrendState.STRONG_UP.value
        elif strong_down_streak >= STRONG_PERSISTENCE_WEEKS:
            state = TrendState.STRONG_DOWN.value
        # 3. First week of a strong condition rides as plain UP/DOWN while the gate waits.
        elif su:
            state = TrendState.UP.value
        elif sd:
            state = TrendState.DOWN.value
        # 4. Plain UP/DOWN with entry/exit hysteresis: enter beyond the neutral band, exit only
        #    when price actually crosses the anchor (dist sign flips) or the slope turns against.
        elif bool(up_raw.iloc[i]) or (
            prev in (TrendState.UP.value, TrendState.STRONG_UP.value)
            and d40 > 0
            and s40 >= -SLOPE_DEAD_ZONE_ATR
        ):
            state = TrendState.UP.value
        elif bool(down_raw.iloc[i]) or (
            prev in (TrendState.DOWN.value, TrendState.STRONG_DOWN.value)
            and d40 < 0
            and s40 <= SLOPE_DEAD_ZONE_ATR
        ):
            state = TrendState.DOWN.value
        else:
            state = TrendState.TRANSITION.value
        states.append(state)
        dates.append(f["date"].iloc[i])
        prev = state

    return pd.DataFrame(
        {
            "date": dates,
            "state": states,
            "slope40_atr": slope40.iloc[first:].round(3).tolist(),
            "slope10_atr": slope10.iloc[first:].round(3).tolist(),
            "dist40_atr": dist40.iloc[first:].round(3).tolist(),
        }
    )


def classify_trend(frame: pd.DataFrame, *, symbol: str = "", as_of: str | None = None) -> TrendSnapshot:
    """Latest trend state for one symbol, with dwell time and the prior state."""
    series = classify_trend_series(frame)
    if series.empty:
        return TrendSnapshot(
            symbol=symbol, as_of=as_of, state=None, prior_state=None, weeks_in_state=0,
            entered_at=None, slope40_atr=None, slope10_atr=None, dist40_atr=None, thin_history=True,
        )
    states = series["state"].tolist()
    current = states[-1]
    run = 1
    for value in reversed(states[:-1]):
        if value != current:
            break
        run += 1
    prior = states[-1 - run] if run < len(states) else None
    entered = series["date"].iloc[len(states) - run]

    def _val(column: str) -> float | None:
        v = series[column].iloc[-1]
        return float(v) if pd.notna(v) else None

    return TrendSnapshot(
        symbol=symbol,
        as_of=as_of,
        state=current,
        prior_state=prior,
        weeks_in_state=run,
        entered_at=str(pd.Timestamp(entered).date()),
        slope40_atr=_val("slope40_atr"),
        slope10_atr=_val("slope10_atr"),
        dist40_atr=_val("dist40_atr"),
        thin_history=False,
    )
