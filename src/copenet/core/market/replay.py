"""Point-in-time replay harness for the Insight Engine.

Reuses the SAME feature path as live (`compute_features`) — the snapshot (frame sliced to `as_of`) is
the only thing that changes. Forward returns are computed in a SEPARATE label phase and never enter
the feature extractor. Episode de-dup (only the first week a pattern fires) keeps samples
independent-ish. See docs/plans/MARKET_INSIGHT_ENGINE.md §9.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from .data_sources import fetch_ohlcv
from .features import compute_features


def _sorted(frame: pd.DataFrame) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])
    f = frame.copy()
    f["date"] = pd.to_datetime(f["date"])
    return f.dropna(subset=["close"]).sort_values("date").reset_index(drop=True)


def generate_soft_bottoming_events(
    symbols: list[str],
    *,
    horizon_weeks: int = 8,
    benchmark: str = "VOO",
    period: str = "8y",
    min_history: int = 44,
) -> list[dict[str, Any]]:
    """Walk each symbol week-by-week (split-adjusted), flag soft_bottoming episode-starts as-of each
    date, then label the realized forward return / MAE / benchmark-relative outcome / regime."""
    bench = _sorted(fetch_ohlcv(benchmark, interval="1wk", period=period, auto_adjust=True))
    bench_close = bench.set_index("date")["close"].astype(float) if not bench.empty else pd.Series(dtype=float)

    events: list[dict[str, Any]] = []
    for symbol in symbols:
        try:
            f = _sorted(fetch_ohlcv(symbol, interval="1wk", period=period, auto_adjust=True))
        except Exception:
            continue
        n = len(f)
        if n < min_history + horizon_weeks + 4:
            continue
        close = f["close"].astype(float)
        prev = False
        for i in range(min_history, n - horizon_weeks):
            as_of = f["date"].iloc[i]
            # PRODUCTION feature path, on the as-of snapshot only (no future bars reachable)
            fs = compute_features(
                f.iloc[: i + 1],
                bench[bench["date"] <= as_of] if not bench.empty else None,
                symbol=symbol,
                as_of=str(as_of.date()),
            )
            flag = fs.soft_bottoming
            if flag and not prev:  # episode start = one independent-ish sample
                entry = float(close.iloc[i])
                window = close.iloc[i : i + horizon_weeks + 1]
                fwd_return = (float(close.iloc[i + horizon_weeks]) / entry - 1) * 100
                mae = (float(window.min()) / entry - 1) * 100

                beat_bench = False
                regime = "unknown"
                if not bench_close.empty:
                    past = bench_close[bench_close.index <= as_of]
                    fut = bench_close[bench_close.index > as_of]
                    if len(past) >= 14 and len(fut) >= horizon_weeks:
                        b_entry = float(past.iloc[-1])
                        bench_fwd = (float(fut.iloc[horizon_weeks - 1]) / b_entry - 1) * 100
                        beat_bench = fwd_return > bench_fwd
                        regime = "bull" if b_entry >= float(past.iloc[-14]) else "bear"

                events.append(
                    {
                        "symbol": symbol,
                        "as_of": str(as_of.date()),
                        "score": fs.soft_bottoming_score,
                        "drawdown": fs.drawdown_pct,
                        "fwd_return": round(fwd_return, 2),
                        "mae": round(mae, 2),
                        "beat_bench": beat_bench,
                        "regime": regime,
                    }
                )
            prev = flag
    return events
