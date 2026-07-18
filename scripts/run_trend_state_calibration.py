"""Calibration report for the 5-state trend classifier (Signal Engine v2, inch #1).

Walks every non-macro universe symbol over 8 years of weekly bars and measures what the
classifier DOES — state distribution, dwell times, transition flows, forward returns per
state (absolute and vs VOO), and a current-state diff against the old binary trend rule.

This is a MEASUREMENT, not a tuner: the classifier's constants are pre-registered in
trend_states.py. The histogram tells us whether the quantization is sane (TRANSITION
should hold roughly 20-35%% of weeks); the forward returns tell us whether the states
mean anything. Forward-return samples are overlapping weeks — descriptive, not
independent trials.

Usage: uv run python scripts/run_trend_state_calibration.py [--period 8y] [--out PATH]
"""

from __future__ import annotations

import argparse
import json
import time
from collections import defaultdict
from datetime import date
from pathlib import Path

import pandas as pd

from copenet.core.market.data_sources import fetch_ohlcv
from copenet.core.market.signals import compute_price_signals
from copenet.core.market.trend_states import (
    DIST_NEUTRAL_ATR,
    SLOPE_DEAD_ZONE_ATR,
    STRONG_PERSISTENCE_WEEKS,
    TREND_STATE_VERSION,
    classify_trend,
    classify_trend_series,
)
from copenet.core.market.universe import UNIVERSE

STATES = ["strong_up", "up", "transition", "down", "strong_down"]
HORIZONS = (4, 8)


def _fetch_weekly(symbol: str, period: str) -> pd.DataFrame:
    f = fetch_ohlcv(symbol, interval="1wk", period=period, auto_adjust=True)
    if f is None or f.empty:
        return pd.DataFrame()
    f = f.copy()
    f["date"] = pd.to_datetime(f["date"])
    if getattr(f["date"].dt, "tz", None) is not None:
        f["date"] = f["date"].dt.tz_localize(None)
    return f.dropna(subset=["close"]).sort_values("date").reset_index(drop=True)


def _forward_returns(closes: pd.Series, horizon: int) -> pd.Series:
    return (closes.shift(-horizon) / closes - 1) * 100


def _runs(states: list[str]) -> list[tuple[str, int]]:
    runs: list[tuple[str, int]] = []
    for state in states:
        if runs and runs[-1][0] == state:
            runs[-1] = (state, runs[-1][1] + 1)
        else:
            runs.append((state, 1))
    return runs


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--period", default="8y")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    symbols = [a for a in UNIVERSE if a.role != "macro"]
    bench = _fetch_weekly("VOO", args.period)
    bench_fwd = {
        h: _forward_returns(bench.set_index("date")["close"].astype(float), h) for h in HORIZONS
    }

    week_counts: dict[str, int] = defaultdict(int)
    dwell: dict[str, list[int]] = defaultdict(list)
    transitions: dict[str, int] = defaultdict(int)
    fwd_samples: dict[tuple[str, int], list[float]] = defaultdict(list)
    excess_samples: dict[tuple[str, int], list[float]] = defaultdict(list)
    per_symbol: dict[str, dict[str, float]] = {}
    current: list[dict] = []
    skipped: list[dict] = []

    for asset in symbols:
        try:
            frame = _fetch_weekly(asset.symbol, args.period)
        except Exception as exc:  # network/vendor hiccup — report, don't die
            skipped.append({"symbol": asset.symbol, "reason": f"fetch failed: {exc}"})
            continue
        series = classify_trend_series(frame)
        if series.empty:
            skipped.append({"symbol": asset.symbol, "reason": f"insufficient history ({len(frame)} wk)"})
            continue

        merged = series.merge(frame[["date", "close"]], on="date", how="left")
        closes = merged["close"].astype(float)
        for h in HORIZONS:
            merged[f"fwd{h}"] = _forward_returns(closes, h)
            bf = bench_fwd[h].reindex(merged["date"]).to_numpy()
            merged[f"excess{h}"] = merged[f"fwd{h}"].to_numpy() - bf

        states = merged["state"].tolist()
        counts = merged["state"].value_counts()
        per_symbol[asset.symbol] = {
            s: round(float(counts.get(s, 0)) / len(states) * 100, 1) for s in STATES
        }
        for s, c in counts.items():
            week_counts[s] += int(c)
        runs = _runs(states)
        for s, length in runs:
            dwell[s].append(length)
        for (a, _), (b, _) in zip(runs, runs[1:], strict=False):
            transitions[f"{a}->{b}"] += 1
        for h in HORIZONS:
            valid = merged.dropna(subset=[f"fwd{h}"])
            for s in STATES:
                rows = valid[valid["state"] == s]
                fwd_samples[(s, h)].extend(rows[f"fwd{h}"].tolist())
                excess_samples[(s, h)].extend(rows[f"excess{h}"].dropna().tolist())

        snap = classify_trend(frame, symbol=asset.symbol)
        old = compute_price_signals(frame)
        old_dir = old.trend_direction
        new_family = "up" if snap.state in ("strong_up", "up") else (
            "down" if snap.state in ("strong_down", "down") else "transition"
        )
        current.append(
            {
                "symbol": asset.symbol,
                "name": asset.name,
                "role": asset.role,
                "state": snap.state,
                "weeks_in_state": snap.weeks_in_state,
                "entered_at": snap.entered_at,
                "prior_state": snap.prior_state,
                "slope40_atr": snap.slope40_atr,
                "dist40_atr": snap.dist40_atr,
                "old_direction": old_dir,
                "changed_call": new_family != old_dir,
            }
        )
        time.sleep(0.2)  # be polite to Yahoo

    total_weeks = sum(week_counts.values())
    forward = {}
    for s in STATES:
        forward[s] = {}
        for h in HORIZONS:
            vals = pd.Series(fwd_samples[(s, h)], dtype=float)
            exc = pd.Series(excess_samples[(s, h)], dtype=float)
            forward[s][f"{h}w"] = {
                "n": int(len(vals)),
                "median": round(float(vals.median()), 2) if len(vals) else None,
                "mean": round(float(vals.mean()), 2) if len(vals) else None,
                "win_rate": round(float((vals > 0).mean()) * 100, 1) if len(vals) else None,
                "excess_median": round(float(exc.median()), 2) if len(exc) else None,
                "beat_voo": round(float((exc > 0).mean()) * 100, 1) if len(exc) else None,
            }

    report = {
        "generated": str(date.today()),
        "period": args.period,
        "version": TREND_STATE_VERSION,
        "constants": {
            "slope_dead_zone_atr": SLOPE_DEAD_ZONE_ATR,
            "dist_neutral_atr": DIST_NEUTRAL_ATR,
            "strong_persistence_weeks": STRONG_PERSISTENCE_WEEKS,
        },
        "symbols_used": [a.symbol for a in symbols if a.symbol in per_symbol],
        "skipped": skipped,
        "total_state_weeks": total_weeks,
        "distribution_pct": {
            s: round(week_counts[s] / total_weeks * 100, 1) if total_weeks else 0.0 for s in STATES
        },
        "dwell_weeks": {
            s: {
                "episodes": len(dwell[s]),
                "mean": round(float(pd.Series(dwell[s]).mean()), 1) if dwell[s] else None,
                "median": float(pd.Series(dwell[s]).median()) if dwell[s] else None,
                "max": int(max(dwell[s])) if dwell[s] else None,
            }
            for s in STATES
        },
        "transitions": dict(sorted(transitions.items(), key=lambda kv: -kv[1])),
        "forward_returns": forward,
        "current": sorted(current, key=lambda row: STATES.index(row["state"]) if row["state"] else 99),
        "per_symbol_distribution": per_symbol,
    }

    out = Path(args.out) if args.out else Path(f"trend_state_calibration_{date.today()}.json")
    out.write_text(json.dumps(report, indent=2))

    print(f"\n=== 5-state trend calibration · {args.period} · {len(per_symbol)} symbols · {total_weeks} state-weeks ===")
    print("\nState distribution (% of all weeks):")
    for s in STATES:
        print(f"  {s:<12} {report['distribution_pct'][s]:>5.1f}%")
    print("\nDwell (weeks/episode, median):")
    for s in STATES:
        d = report["dwell_weeks"][s]
        print(f"  {s:<12} median {d['median']} · mean {d['mean']} · {d['episodes']} episodes · max {d['max']}")
    print("\nForward returns by state (8w):")
    for s in STATES:
        f8 = forward[s]["8w"]
        print(
            f"  {s:<12} n={f8['n']:>5} · median {f8['median']:>6}% · win {f8['win_rate']}% · "
            f"excess-vs-VOO median {f8['excess_median']}% · beat VOO {f8['beat_voo']}%"
        )
    print("\nCurrent calls (● = differs from old binary rule):")
    for row in report["current"]:
        marker = "●" if row["changed_call"] else " "
        print(
            f"  {marker} {row['symbol']:<6} {row['state'] or 'n/a':<12} "
            f"({row['weeks_in_state']}wk, since {row['entered_at']}) old={row['old_direction']}"
        )
    if skipped:
        print("\nSkipped:")
        for item in skipped:
            print(f"  {item['symbol']}: {item['reason']}")
    print(f"\nFull report: {out}")


if __name__ == "__main__":
    main()
