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
    # A cockpit comparison should answer how the asset is behaving now, not turn a
    # decades-old split-adjusted starting price into a six-figure lifetime verdict.
    # Fifty-three weekly closes produce a consistent trailing-52-week comparison.
    joined = joined.tail(53)
    if len(joined) < 8:
        return VerdictRow(
            bench=bench,
            label="In line",
            excess_return_pct=None,
            asset_return_pct=None,
            benchmark_return_pct=None,
            beta=None,
            beta_adjusted_excess_pct=None,
            tone="flat",
        )
    returns = joined.pct_change().dropna()
    asset_total = joined["asset"].iloc[-1] / joined["asset"].iloc[0] - 1
    bench_total = joined["bench"].iloc[-1] / joined["bench"].iloc[0] - 1
    variance = float(returns["bench"].var())
    beta = float(returns["asset"].cov(returns["bench"]) / variance) if variance else 1.0
    # The benchmark verdict answers the plain-English question operators expect:
    # did the asset beat the benchmark over the same dates? Beta adjustment is useful
    # context, but it must not reverse the headline and masquerade as relative return.
    excess_return = (asset_total - bench_total) * 100
    beta_adjusted_excess = (asset_total - (beta * bench_total)) * 100
    if math.isfinite(excess_return) and abs(excess_return) < 0.05:
        excess_return = 0.0
    if math.isfinite(beta_adjusted_excess) and abs(beta_adjusted_excess) < 0.05:
        beta_adjusted_excess = 0.0
    if excess_return > 2:
        label, tone = "Beats", "up"
    elif excess_return < -2:
        label, tone = "Lags", "down"
    else:
        label, tone = "In line", "flat"
    finite = math.isfinite
    return VerdictRow(
        bench=bench,
        label=label,
        excess_return_pct=round(float(excess_return), 4) if finite(excess_return) else None,
        asset_return_pct=round(float(asset_total * 100), 4) if finite(asset_total) else None,
        benchmark_return_pct=round(float(bench_total * 100), 4) if finite(bench_total) else None,
        beta=round(float(beta), 4) if finite(beta) else None,
        beta_adjusted_excess_pct=round(float(beta_adjusted_excess), 4) if finite(beta_adjusted_excess) else None,
        tone=tone,  # type: ignore[arg-type]
    )


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
