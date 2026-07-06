"""Pure pandas signal math for Market Monitor."""

from __future__ import annotations

import math
from typing import Any

import pandas as pd

from .models import PriceSignals, RrgSector


def compute_price_signals(frame: pd.DataFrame, benchmark: pd.DataFrame | None = None) -> PriceSignals:
    prices = _normalized_frame(frame)
    if prices.empty:
        return PriceSignals("n/a", "n/a", "n/a", 0, "down", "no price history", False, thin_history=True)

    close = prices["close"].astype(float)
    last = float(close.iloc[-1])
    thin = len(close) < 40
    ma10 = close.rolling(10, min_periods=10).mean()
    ma30 = close.rolling(30, min_periods=30).mean()
    ma40 = close.rolling(40, min_periods=40).mean()
    rsi = _rsi(close)
    drawdown_pct = _drawdown(close)
    atr_move = _atr_move(prices)
    volume_vs_avg = _volume_vs_average(prices)
    rs = _relative_strength(close, benchmark)
    mama = _mama_regime(close)

    if thin:
        direction: str = "up" if last >= float(close.iloc[0]) else "down"
        return PriceSignals(
            below_ma="n/a",
            drawdown=_fmt_pct(drawdown_pct),
            rsi=_fmt_number(float(rsi.iloc[-1])) if not rsi.dropna().empty else "n/a",
            confluence=1 if drawdown_pct <= -20 else 0,
            trend_direction=direction,  # type: ignore[arg-type]
            trend_note="short history; trend math limited",
            confirmed=direction == "up",
            relative_strength=rs,
            mama_regime=mama,
            atr_move=atr_move,
            volume_vs_avg=volume_vs_avg,
            thin_history=True,
        )

    ma_anchor = float(ma40.iloc[-1])
    below_ma = ((last / ma_anchor) - 1) * 100 if ma_anchor else 0.0
    above_stack = last > float(ma10.iloc[-1]) > float(ma30.iloc[-1]) > float(ma40.iloc[-1])
    below_stack = last < float(ma10.iloc[-1]) < float(ma30.iloc[-1]) < float(ma40.iloc[-1])
    direction = "up" if above_stack or last > float(ma40.iloc[-1]) or last > float(close.iloc[0]) else "down"
    if below_stack:
        direction = "down"
    rsi_last = float(rsi.iloc[-1]) if not rsi.dropna().empty else 50.0
    confluence = 0
    confluence += 1 if below_ma <= -3 else 0
    confluence += 1 if drawdown_pct <= -20 else 0
    confluence += 1 if rsi_last <= 40 else 0
    confluence += 1 if last > float(ma10.iloc[-1]) and close.iloc[-2] <= ma10.iloc[-2] else 0
    note = "above weekly moving-average stack" if direction == "up" else "below weekly trend stack"
    return PriceSignals(
        below_ma=_fmt_pct(below_ma),
        drawdown=_fmt_pct(drawdown_pct),
        rsi=_fmt_number(rsi_last),
        confluence=max(0, min(4, confluence)),
        trend_direction=direction,  # type: ignore[arg-type]
        trend_note=note,
        confirmed=direction == "up" and last >= float(ma10.iloc[-1]),
        relative_strength=rs,
        mama_regime=mama,
        atr_move=atr_move,
        volume_vs_avg=volume_vs_avg,
        thin_history=False,
    )


# (rolling window, momentum diff period, EMA smooth, tail points) per rotation speed.
# All modes use weekly log-relative-strength against the benchmark. Fast reacts in a few
# weeks (tactical); slow needs a couple quarters to turn (macro-cycle rotation).
_RRG_MODES: dict[str, tuple[int, int, int, int]] = {
    "fast": (8, 2, 2, 6),
    "default": (13, 4, 3, 10),
    "slow": (26, 8, 5, 12),
}


def _rrg_axes(rs: pd.Series, window: int, mom_period: int, smooth: int) -> tuple[pd.Series, pd.Series]:
    """Return RRG-style axes from one shared weekly relative-strength source.

    X is normalized relative-strength level. Y is normalized relative-strength slope.
    Momentum is intentionally computed from smoothed log-RS directly, not from X.diff(),
    so rolling mean/std changes in X do not create fake rotation wiggle.
    """
    log_rs = rs.map(math.log)
    smoothed = log_rs.ewm(span=smooth, adjust=False, min_periods=1).mean()
    min_periods = max(2, window // 2)
    x = _zscore(smoothed, window=window, min_periods=min_periods)
    y = _zscore(smoothed.diff(mom_period), window=window, min_periods=min_periods)
    return x, y


def compute_rrg_tail(symbol: str, name: str, frame: pd.DataFrame, benchmark: pd.DataFrame) -> RrgSector:
    asset = _normalized_frame(frame)
    bench = _normalized_frame(benchmark)
    if asset.empty or bench.empty:
        return RrgSector(symbol=symbol, name=name, tail=[], quadrant="lagging", tails={})
    joined = pd.concat(
        [asset.set_index("date")["close"].rename("asset"), bench.set_index("date")["close"].rename("bench")],
        axis=1,
        join="inner",
    ).dropna()
    if len(joined) < 8:
        return RrgSector(symbol=symbol, name=name, tail=[], quadrant="lagging", tails={})
    rs = (joined["asset"] / joined["bench"]).dropna()
    rs = rs[rs > 0]
    if len(rs) < 8:
        return RrgSector(symbol=symbol, name=name, tail=[], quadrant="lagging", tails={})

    tails: dict[str, list[dict[str, float]]] = {}
    for mode, (window, mom_period, smooth, points) in _RRG_MODES.items():
        x, y = _rrg_axes(rs, window, mom_period, smooth)
        tails[mode] = [
            {"x": round(float(px), 2), "y": round(float(py), 2)}
            for px, py in zip(x.tail(points).tolist(), y.tail(points).tolist(), strict=False)
            if math.isfinite(float(px)) and math.isfinite(float(py))
        ]

    tail = tails.get("default", [])
    last = tail[-1] if tail else {"x": -1.0, "y": -1.0}
    if last["x"] >= 0 and last["y"] >= 0:
        quadrant = "leading"
    elif last["x"] >= 0 and last["y"] < 0:
        quadrant = "weakening"
    elif last["x"] < 0 and last["y"] < 0:
        quadrant = "lagging"
    else:
        quadrant = "improving"
    return RrgSector(symbol=symbol, name=name, tail=tail, quadrant=quadrant, tails=tails)  # type: ignore[arg-type]


def _normalized_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])
    renamed = {str(column).lower(): column for column in frame.columns}
    out = pd.DataFrame(
        {
            "date": frame[renamed.get("date", renamed.get("datetime", frame.columns[0]))],
            "open": frame[renamed.get("open", "open")],
            "high": frame[renamed.get("high", "high")],
            "low": frame[renamed.get("low", "low")],
            "close": frame[renamed.get("close", "close")],
            "volume": frame[renamed.get("volume", "volume")] if "volume" in renamed else 0,
        }
    )
    out = out.dropna(subset=["close"]).copy()
    out["date"] = pd.to_datetime(out["date"], utc=True)
    return out.sort_values("date").reset_index(drop=True)


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period, min_periods=period).mean()
    loss = (-delta.clip(upper=0)).rolling(period, min_periods=period).mean()
    rs = gain / loss.replace(0, math.nan)
    return 100 - (100 / (1 + rs))


def _drawdown(close: pd.Series) -> float:
    window = close.tail(min(len(close), 52))
    high = float(window.max()) if not window.empty else 0.0
    last = float(close.iloc[-1])
    return ((last / high) - 1) * 100 if high else 0.0


def _atr_move(prices: pd.DataFrame, period: int = 14) -> str:
    if len(prices) < period + 1:
        return "n/a"
    high = prices["high"].astype(float)
    low = prices["low"].astype(float)
    close = prices["close"].astype(float)
    previous_close = close.shift(1)
    tr = pd.concat([(high - low), (high - previous_close).abs(), (low - previous_close).abs()], axis=1).max(axis=1)
    atr = float(tr.rolling(period, min_periods=period).mean().iloc[-1])
    move = abs(float(close.iloc[-1] - close.iloc[-2]))
    return f"{move / atr:.1f}x ATR" if atr else "n/a"


def _volume_vs_average(prices: pd.DataFrame) -> str:
    if "volume" not in prices or len(prices) < 20:
        return "n/a"
    volume = prices["volume"].astype(float)
    avg = float(volume.rolling(20, min_periods=20).mean().iloc[-1])
    return f"{float(volume.iloc[-1]) / avg:.1f}x avg" if avg else "n/a"


def _relative_strength(close: pd.Series, benchmark: pd.DataFrame | None) -> str:
    if benchmark is None or benchmark.empty:
        return "n/a"
    bench = _normalized_frame(benchmark)["close"].astype(float)
    periods = min(len(close), len(bench), 26)
    if periods < 2:
        return "n/a"
    asset_return = close.iloc[-1] / close.iloc[-periods] - 1
    bench_return = bench.iloc[-1] / bench.iloc[-periods] - 1
    return _fmt_pct((asset_return - bench_return) * 100)


def _mama_regime(close: pd.Series) -> str:
    if len(close) < 10:
        return "n/a"
    fast = close.ewm(span=10, adjust=False).mean().iloc[-1]
    slow = close.ewm(span=21, adjust=False).mean().iloc[-1]
    return "MAMA above FAMA" if fast >= slow else "MAMA below FAMA"


def _zscore(series: pd.Series, window: int = 10, min_periods: int = 4) -> pd.Series:
    rolling = series.rolling(window, min_periods=min_periods)
    mean = rolling.mean()
    std = rolling.std().replace(0, math.nan)
    return ((series - mean) / std).fillna(0)


def _fmt_pct(value: float) -> str:
    if not math.isfinite(value):
        return "n/a"
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.1f}%"


def _fmt_number(value: float) -> str:
    if not math.isfinite(value):
        return "n/a"
    return f"{value:.0f}"
