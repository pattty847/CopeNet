"""Calendar-horizon outcomes, separate from the production feature extractor."""
from __future__ import annotations

import numpy as np
import pandas as pd

HORIZONS = (4, 12, 26)


def measure_outcome(daily: pd.DataFrame, benchmark: pd.DataFrame,
                    signal_week: pd.Timestamp, weeks: int,
                    cutoff: pd.Timestamp) -> dict:
    # Weekly bars carry Monday labels. The decision is made after that week ends.
    next_week = signal_week + pd.Timedelta(days=7)
    future = benchmark[benchmark.date >= next_week]
    if future.empty:
        return {"status": "pending"}
    entry_date = future.date.iloc[0]
    end = entry_date + pd.Timedelta(weeks=weeks)
    if end > cutoff:
        return {"status": "pending"}
    if benchmark.date.max() < end:
        return {"status": "missing_followup"}
    bench = future[future.date < end]
    path = daily[(daily.date >= entry_date) & (daily.date < end)]
    if path.date.tolist() != bench.date.tolist() or len(path) < 2:
        return {"status": "missing_sessions"}
    entry = float(path.open.iloc[0])
    bench_entry = float(bench.open.iloc[0])
    if entry <= 0 or bench_entry <= 0:
        return {"status": "invalid_entry"}
    closes = np.r_[entry, path.close.to_numpy(dtype=float)]
    returns = closes[1:] / closes[:-1] - 1
    ret = (closes[-1] / entry - 1) * 100
    benchmark_return = (float(bench.close.iloc[-1]) / bench_entry - 1) * 100
    underwater = path.close.to_numpy() < entry
    recovery = None
    if underwater.any():
        first_loss = int(np.flatnonzero(underwater)[0])
        recovered = np.flatnonzero(~underwater[first_loss + 1:])
        if len(recovered):
            recovery = int((path.date.iloc[first_loss + 1 + recovered[0]] - entry_date).days)
    return {
        "status": "complete", "entry_date": str(entry_date.date()),
        "exit_date": str(path.date.iloc[-1].date()), "return_pct": ret,
        "benchmark_return_pct": benchmark_return, "excess_pct": ret - benchmark_return,
        "mae_pct": min(0.0, (float(path.low.min()) / entry - 1) * 100),
        "mfe_pct": max(0.0, (float(path.high.max()) / entry - 1) * 100),
        # Close-to-close peak/trough drawdown; MAE above separately includes intraday lows.
        "max_drawdown_pct": float((closes / np.maximum.accumulate(closes) - 1).min() * 100),
        "annualized_vol_pct": float(np.std(returns, ddof=1) * np.sqrt(252) * 100),
        "went_underwater": bool(underwater.any()), "recovery_days": recovery,
    }
