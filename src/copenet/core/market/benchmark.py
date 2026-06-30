"""Risk-adjusted benchmark verdicts."""

from __future__ import annotations

import math

import pandas as pd

from .models import VerdictRow


def benchmark_verdict(asset: pd.DataFrame, benchmarks: dict[str, pd.DataFrame]) -> list[VerdictRow]:
    verdicts: list[VerdictRow] = []
    for bench, frame in benchmarks.items():
        verdicts.append(_one_verdict(asset, frame, bench))
    return verdicts


def _one_verdict(asset: pd.DataFrame, benchmark: pd.DataFrame, bench: str) -> VerdictRow:
    joined = pd.concat(
        [_close(asset).rename("asset"), _close(benchmark).rename("bench")],
        axis=1,
        join="inner",
    ).dropna()
    if len(joined) < 8:
        return VerdictRow(bench=bench, label="In line", pct="n/a", tone="flat")
    returns = joined.pct_change().dropna()
    asset_total = joined["asset"].iloc[-1] / joined["asset"].iloc[0] - 1
    bench_total = joined["bench"].iloc[-1] / joined["bench"].iloc[0] - 1
    variance = float(returns["bench"].var())
    beta = float(returns["asset"].cov(returns["bench"]) / variance) if variance else 1.0
    risk_adjusted_excess = (asset_total - (beta * bench_total)) * 100
    if risk_adjusted_excess > 2:
        label, tone = "Beats", "up"
    elif risk_adjusted_excess < -2:
        label, tone = "Lags", "down"
    else:
        label, tone = "In line", "flat"
    pct = "n/a" if not math.isfinite(risk_adjusted_excess) else f"{risk_adjusted_excess:+.1f}%"
    return VerdictRow(bench=bench, label=label, pct=pct, tone=tone)  # type: ignore[arg-type]


def _close(frame: pd.DataFrame) -> pd.Series:
    if frame.empty:
        return pd.Series(dtype=float)
    columns = {str(column).lower(): column for column in frame.columns}
    date_column = columns.get("date", frame.columns[0])
    close_column = columns.get("close")
    if close_column is None:
        return pd.Series(dtype=float)
    out = frame[[date_column, close_column]].copy()
    out[date_column] = pd.to_datetime(out[date_column], utc=True)
    return out.set_index(date_column)[close_column].astype(float)
