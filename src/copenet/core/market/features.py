"""Typed numeric feature extraction from OHLCV — the foundation of the Insight Engine.

Design (see docs/plans/MARKET_INSIGHT_ENGINE.md §9):
- PURE function of the supplied frame. It can only see the bars it is given, so a frame sliced to
  `as_of` makes lookahead structurally impossible — there is no path to a future bar.
- Emits TYPED NUMERIC facts (with units/lookback baked into the name). Text belongs in the formatter.
- Includes DATA-QUALITY features so downstream (and the model) know when the facts are weak.
- One flagship shape descriptor: `soft_bottoming` — decomposed + auditable, with a PRE-REGISTERED
  definition + threshold (do not tune to maximize a backtest; the backtest measures its base rate).
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

FEATURE_CATALOG_VERSION = "v1"

# Pre-registered soft-bottoming definition (threshold fixed BEFORE backtesting — calibration, not mining).
SB_SCORE_THRESHOLD = 0.6
SB_MIN_DRAWDOWN = -10.0  # soft bottoming only applies after a real decline


@dataclass(frozen=True)
class FeatureSet:
    symbol: str
    as_of: str | None
    basis: str
    # returns (%), weekly frame
    r_1w: float | None
    r_4w: float | None
    r_13w: float | None
    r_26w: float | None
    r_52w: float | None
    r_ytd: float | None
    # benchmark-relative
    excess_13w: float | None
    excess_26w: float | None
    beta_52w: float | None
    corr_52w: float | None
    # volatility (annualized %)
    vol_4w: float | None
    vol_13w: float | None
    vol_26w: float | None
    atr_pct: float | None
    atr_move: float | None
    atr_pctile: float | None
    # trend / moving averages
    dist_ma10: float | None
    dist_ma30: float | None
    dist_ma40: float | None
    slope_ma10: float | None
    slope_ma30: float | None
    slope_ma40: float | None
    ma_stack: str
    # drawdown / position
    drawdown_pct: float | None
    weeks_since_high: int | None
    pct_52w: float | None
    # volume
    vol_vs_avg: float | None
    up_down_vol: float | None
    # relative strength (RRG-style)
    rs_ratio: float | None
    rs_momentum: float | None
    rsi_14: float | None
    # data quality
    history_weeks: int
    has_volume: bool
    thin_history: bool
    # soft bottoming (decomposed + score)
    sb_lower_lows_stopped: bool
    sb_higher_low: bool
    sb_ma_reclaim: bool
    sb_drawdown_stabilized: bool
    sb_rs_improving: bool
    sb_volume_drying: bool
    sb_momentum_divergence: bool
    soft_bottoming_score: float
    soft_bottoming: bool

    def to_dict(self) -> dict:
        return asdict(self)


def _f(value: float | int | None) -> float | None:
    """NaN/inf → None; round to keep facts tidy."""
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(v) or math.isinf(v):
        return None
    return round(v, 4)


def _normalize(frame: pd.DataFrame) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])
    cols = {str(c).lower(): c for c in frame.columns}
    out = pd.DataFrame()
    date_col = cols.get("date") or cols.get("datetime")
    out["date"] = pd.to_datetime(frame[date_col]) if date_col else pd.to_datetime(frame.index)
    for name in ("open", "high", "low", "close", "volume"):
        out[name] = pd.to_numeric(frame[cols[name]], errors="coerce") if name in cols else np.nan
    return out.dropna(subset=["close"]).sort_values("date").reset_index(drop=True)


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period, min_periods=period).mean()
    loss = (-delta.clip(upper=0)).rolling(period, min_periods=period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _atr(frame: pd.DataFrame, period: int = 14) -> pd.Series:
    high, low, close = frame["high"], frame["low"], frame["close"]
    prev_close = close.shift(1)
    tr = pd.concat([(high - low), (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    return tr.rolling(period, min_periods=period).mean()


def _ret(close: pd.Series, bars: int) -> float | None:
    if len(close) <= bars:
        return None
    prev = close.iloc[-1 - bars]
    return ((close.iloc[-1] / prev) - 1) * 100 if prev else None


def _ann_vol(close: pd.Series, bars: int) -> float | None:
    if len(close) <= bars:
        return None
    rets = close.pct_change().dropna().iloc[-bars:]
    if len(rets) < 3:
        return None
    return float(rets.std() * math.sqrt(52) * 100)


def _rs_pair(close: pd.Series, bench: pd.Series) -> tuple[float | None, float | None]:
    """RRG-style RS-Ratio (% deviation of relative strength from its mean) + RS-Momentum (z-scored)."""
    pair = pd.concat([close.rename("a"), bench.rename("b")], axis=1).dropna()
    if len(pair) < 16:
        return None, None
    rs = pair["a"] / pair["b"]
    center = rs.rolling(10, min_periods=4).mean()
    ratio = ((rs / center) - 1).fillna(0) * 100
    mom = ratio.diff(4).fillna(0)
    z = (mom - mom.mean()) / (mom.std() or 1)
    return _f(ratio.iloc[-1]), _f(z.iloc[-1] * 3)


def compute_features(
    weekly: pd.DataFrame,
    benchmark: pd.DataFrame | None = None,
    *,
    symbol: str = "",
    basis: str = "split_adjusted",
    as_of: str | None = None,
) -> FeatureSet:
    f = _normalize(weekly)
    n = len(f)
    thin = n < 40
    has_volume = bool("volume" in f and f["volume"].fillna(0).sum() > 0)

    if n == 0:
        return _empty(symbol, as_of, basis)

    close = f["close"].astype(float)
    last = float(close.iloc[-1])

    # moving averages
    ma10 = close.rolling(10, min_periods=10).mean()
    ma30 = close.rolling(30, min_periods=30).mean()
    ma40 = close.rolling(40, min_periods=40).mean()

    def dist(ma: pd.Series) -> float | None:
        v = ma.iloc[-1]
        return _f((last / v - 1) * 100) if pd.notna(v) and v else None

    def slope(ma: pd.Series) -> float | None:
        if len(ma.dropna()) < 6:
            return None
        a, b = ma.iloc[-1], ma.iloc[-6]
        return _f((a / b - 1) * 100) if pd.notna(a) and pd.notna(b) and b else None

    m10, m30, m40 = ma10.iloc[-1], ma30.iloc[-1], ma40.iloc[-1]
    if pd.notna(m10) and pd.notna(m30) and pd.notna(m40):
        if last > m10 > m30 > m40:
            stack = "above"
        elif last < m10 < m30 < m40:
            stack = "below"
        else:
            stack = "mixed"
    else:
        stack = "n/a"

    # drawdown / 52w position
    window = close.iloc[-52:] if n >= 1 else close
    hi, lo = float(window.max()), float(window.min())
    drawdown_pct = _f((last / hi - 1) * 100) if hi else None
    weeks_since_high = int(len(window) - 1 - int(np.argmax(window.to_numpy()))) if len(window) else None
    pct_52w = _f((last - lo) / (hi - lo) * 100) if hi > lo else None

    # ATR
    atr = _atr(f)
    atr_last = atr.iloc[-1] if len(atr) else np.nan
    atr_pct = _f(atr_last / last * 100) if pd.notna(atr_last) and last else None
    atr_move = _f(abs(close.iloc[-1] - close.iloc[-2]) / atr_last) if n > 1 and pd.notna(atr_last) and atr_last else None
    atr_clean = atr.dropna()
    atr_pctile = _f((atr_clean <= atr_last).mean() * 100) if len(atr_clean) and pd.notna(atr_last) else None

    # volume
    vol_vs_avg = up_down_vol = None
    if has_volume:
        vol = f["volume"].astype(float)
        avg20 = vol.rolling(20, min_periods=5).mean().iloc[-1]
        vol_vs_avg = _f(vol.iloc[-1] / avg20) if pd.notna(avg20) and avg20 else None
        rets = close.pct_change()
        recent = slice(-13, None)
        up_v = vol[recent][rets[recent] > 0].sum()
        dn_v = vol[recent][rets[recent] < 0].sum()
        up_down_vol = _f(up_v / dn_v) if dn_v else None

    # benchmark-relative
    excess_13w = excess_26w = beta_52w = corr_52w = rs_ratio = rs_momentum = None
    if benchmark is not None:
        b = _normalize(benchmark)
        if not b.empty:
            bench_close = b.set_index("date")["close"].astype(float)
            aclose = f.set_index("date")["close"].astype(float)
            joined = pd.concat([aclose.rename("a"), bench_close.rename("b")], axis=1).dropna()
            if len(joined) > 26:
                bench_ret = lambda series, bars: ((series.iloc[-1] / series.iloc[-1 - bars]) - 1) * 100 if len(series) > bars else None  # noqa: E731
                for bars, attr in ((13, "excess_13w"), (26, "excess_26w")):
                    ar = bench_ret(joined["a"], bars)
                    br = bench_ret(joined["b"], bars)
                    if ar is not None and br is not None:
                        if attr == "excess_13w":
                            excess_13w = _f(ar - br)
                        else:
                            excess_26w = _f(ar - br)
                ar = joined["a"].pct_change().dropna().iloc[-52:]
                br = joined["b"].pct_change().dropna().iloc[-52:]
                pair = pd.concat([ar, br], axis=1).dropna()
                if len(pair) > 20:
                    cov = pair.iloc[:, 0].cov(pair.iloc[:, 1])
                    var = pair.iloc[:, 1].var()
                    beta_52w = _f(cov / var) if var else None
                    corr_52w = _f(pair.iloc[:, 0].corr(pair.iloc[:, 1]))
                rs_ratio, rs_momentum = _rs_pair(joined["a"], joined["b"])

    rsi = _rsi(close)
    rsi_last = _f(rsi.iloc[-1]) if len(rsi.dropna()) else None

    sb = _soft_bottoming(close, ma10, rsi, drawdown_pct, rs_momentum, f if has_volume else None, thin)

    return FeatureSet(
        symbol=symbol,
        as_of=as_of,
        basis=basis,
        r_1w=_f(_ret(close, 1)),
        r_4w=_f(_ret(close, 4)),
        r_13w=_f(_ret(close, 13)),
        r_26w=_f(_ret(close, 26)),
        r_52w=_f(_ret(close, 52)),
        r_ytd=_f(_ytd(f)),
        excess_13w=excess_13w,
        excess_26w=excess_26w,
        beta_52w=beta_52w,
        corr_52w=corr_52w,
        vol_4w=_f(_ann_vol(close, 4)),
        vol_13w=_f(_ann_vol(close, 13)),
        vol_26w=_f(_ann_vol(close, 26)),
        atr_pct=atr_pct,
        atr_move=atr_move,
        atr_pctile=atr_pctile,
        dist_ma10=dist(ma10),
        dist_ma30=dist(ma30),
        dist_ma40=dist(ma40),
        slope_ma10=slope(ma10),
        slope_ma30=slope(ma30),
        slope_ma40=slope(ma40),
        ma_stack=stack,
        drawdown_pct=drawdown_pct,
        weeks_since_high=weeks_since_high,
        pct_52w=pct_52w,
        vol_vs_avg=vol_vs_avg,
        up_down_vol=up_down_vol,
        rs_ratio=rs_ratio,
        rs_momentum=rs_momentum,
        rsi_14=rsi_last,
        history_weeks=n,
        has_volume=has_volume,
        thin_history=thin,
        **sb,
    )


def _ytd(f: pd.DataFrame) -> float | None:
    if f.empty:
        return None
    last_date = f["date"].iloc[-1]
    year_start = f[f["date"].dt.year == last_date.year]
    if len(year_start) < 2:
        return None
    first = float(year_start["close"].iloc[0])
    return ((float(f["close"].iloc[-1]) / first) - 1) * 100 if first else None


def _soft_bottoming(
    close: pd.Series,
    ma10: pd.Series,
    rsi: pd.Series,
    drawdown_pct: float | None,
    rs_momentum: float | None,
    vol_frame: pd.DataFrame | None,
    thin: bool,
) -> dict:
    """Decomposed, auditable soft-bottoming detector (pre-registered definition)."""
    n = len(close)
    blanks = {
        "sb_lower_lows_stopped": False,
        "sb_higher_low": False,
        "sb_ma_reclaim": False,
        "sb_drawdown_stabilized": False,
        "sb_rs_improving": False,
        "sb_volume_drying": False,
        "sb_momentum_divergence": False,
        "soft_bottoming_score": 0.0,
        "soft_bottoming": False,
    }
    if thin or n < 24:
        return blanks

    recent4 = close.iloc[-4:].min()
    prior_8 = close.iloc[-12:-4].min()
    lower_lows_stopped = bool(recent4 > prior_8)

    recent6_low = close.iloc[-6:].min()
    prior_low = close.iloc[-18:-6].min()
    higher_low = bool(recent6_low > prior_low)

    ma_reclaim = bool(
        pd.notna(ma10.iloc[-1]) and close.iloc[-1] > ma10.iloc[-1]
        and (close.iloc[-8:-1] < ma10.iloc[-8:-1]).any()
    )

    drawdown_stabilized = bool(
        drawdown_pct is not None and drawdown_pct <= -15 and close.iloc[-1] > close.iloc[-8:].min() * 1.03
    )

    rs_improving = bool(rs_momentum is not None and rs_momentum > 0)

    volume_drying = False
    if vol_frame is not None:
        vol = vol_frame["volume"].astype(float)
        rets = close.pct_change()
        recent_dn = vol.iloc[-6:][rets.iloc[-6:] < 0]
        prior_dn = vol.iloc[-18:-6][rets.iloc[-18:-6] < 0]
        if len(recent_dn) and len(prior_dn):
            volume_drying = bool(recent_dn.mean() < prior_dn.mean())
        elif len(recent_dn) == 0:
            volume_drying = True  # no recent selling

    momentum_divergence = False
    rsi_clean = rsi.dropna()
    if len(rsi_clean) >= 18:
        price_lower_low = recent6_low <= prior_low * 1.01
        rsi_recent_low = rsi.iloc[-6:].min()
        rsi_prior_low = rsi.iloc[-18:-6].min()
        momentum_divergence = bool(price_lower_low and rsi_recent_low > rsi_prior_low)

    # rs_improving only counts toward the denominator when a benchmark was available
    components = [lower_lows_stopped, higher_low, ma_reclaim, drawdown_stabilized, volume_drying, momentum_divergence]
    if rs_momentum is not None:
        components.append(rs_improving)
    score = sum(1 for c in components if c) / len(components)

    in_decline = drawdown_pct is not None and drawdown_pct <= SB_MIN_DRAWDOWN
    soft_bottoming = bool(score >= SB_SCORE_THRESHOLD and in_decline)

    return {
        "sb_lower_lows_stopped": lower_lows_stopped,
        "sb_higher_low": higher_low,
        "sb_ma_reclaim": ma_reclaim,
        "sb_drawdown_stabilized": drawdown_stabilized,
        "sb_rs_improving": rs_improving,
        "sb_volume_drying": volume_drying,
        "sb_momentum_divergence": momentum_divergence,
        "soft_bottoming_score": round(score, 3),
        "soft_bottoming": soft_bottoming,
    }


def _empty(symbol: str, as_of: str | None, basis: str) -> FeatureSet:
    return FeatureSet(
        symbol=symbol, as_of=as_of, basis=basis,
        r_1w=None, r_4w=None, r_13w=None, r_26w=None, r_52w=None, r_ytd=None,
        excess_13w=None, excess_26w=None, beta_52w=None, corr_52w=None,
        vol_4w=None, vol_13w=None, vol_26w=None, atr_pct=None, atr_move=None, atr_pctile=None,
        dist_ma10=None, dist_ma30=None, dist_ma40=None, slope_ma10=None, slope_ma30=None, slope_ma40=None,
        ma_stack="n/a", drawdown_pct=None, weeks_since_high=None, pct_52w=None,
        vol_vs_avg=None, up_down_vol=None, rs_ratio=None, rs_momentum=None, rsi_14=None,
        history_weeks=0, has_volume=False, thin_history=True,
        sb_lower_lows_stopped=False, sb_higher_low=False, sb_ma_reclaim=False, sb_drawdown_stabilized=False,
        sb_rs_improving=False, sb_volume_drying=False, sb_momentum_divergence=False,
        soft_bottoming_score=0.0, soft_bottoming=False,
    )
