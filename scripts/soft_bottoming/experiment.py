"""Offline replay of the unchanged production detector over frozen cache snapshots."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

from copenet.core.market.features import compute_features
from copenet.core.market.price_cache import PriceCache
from copenet.core.market.price_history import WEEKLY, daily_close_available_at, resample_bars
from .outcomes import HORIZONS, measure_outcome


def frame(bars) -> pd.DataFrame:
    return pd.DataFrame([
        {"date": pd.Timestamp(b.t, unit="s").normalize(), "open": b.o, "high": b.h,
         "low": b.l, "close": b.c, "volume": b.v} for b in bars
    ], columns=["date", "open", "high", "low", "close", "volume"])


def snapshot(cache: PriceCache, symbols: list[str], output: Path, as_of: pd.Timestamp):
    """Freeze only price inputs; never copy account or watchlist documents."""
    frozen = output / "inputs"
    frozen.mkdir(parents=True)
    coverage, frames, weekly = [], {}, {}
    for symbol in sorted(set(symbols + ["VOO"])):
        source = cache.root_dir / f"{symbol}.json"
        if not source.exists():
            coverage.append({"symbol": symbol, "status": "missing"})
            continue
        content = source.read_bytes()
        (frozen / source.name).write_bytes(content)
        history = PriceCache(frozen).load(symbol)
        if history is None:
            coverage.append({"symbol": symbol, "status": "invalid_cache"})
            continue
        observed = min(as_of, pd.Timestamp(history.updated_at))
        bars = [b for b in history.bars if pd.Timestamp(daily_close_available_at(b)) <= observed]
        if not bars:
            coverage.append({"symbol": symbol, "status": "no_completed_bars"})
            continue
        frames[symbol] = frame(bars)
        weekly[symbol] = frame(resample_bars(bars, WEEKLY))
        completed_before = observed.tz_convert("America/New_York").tz_localize(None).normalize()
        weekly[symbol] = weekly[symbol][weekly[symbol].date + pd.Timedelta(days=7) <= completed_before].reset_index(drop=True)
        coverage.append({"symbol": symbol, "status": "cached", "bars": len(bars),
                         "first": str(frames[symbol].date.min().date()),
                         "last": str(frames[symbol].date.max().date()),
                         "updated_at": history.updated_at,
                         "sha256": hashlib.sha256(content).hexdigest()})
    (output / "coverage.json").write_text(json.dumps(coverage, indent=2))
    return frames, weekly


def replay(daily: dict, weekly: dict, symbols: list[str], start: pd.Timestamp,
           cutoff: pd.Timestamp, output: Path) -> list[dict]:
    benchmark = weekly["VOO"]
    rows = []
    for number, symbol in enumerate(symbols, 1):
        if symbol not in weekly:
            continue
        stock = weekly[symbol]
        previous = False
        records = []
        for i in range(43, len(stock)):
            date = stock.date.iloc[i]
            # Exclude the current, incomplete calendar week, including holiday ambiguity.
            if date + pd.Timedelta(days=7) > cutoff:
                break
            bench = benchmark[benchmark.date <= date]
            if len(bench) < 44 or bench.date.iloc[-1] != date:
                previous = False
                continue
            # Require the latest 44 weeks to align with benchmark weeks (no silent holes).
            if stock.date.iloc[i-43:i+1].tolist() != bench.date.iloc[-44:].tolist():
                previous = False
                continue
            if date < start - pd.Timedelta(weeks=1):
                continue
            features = compute_features(stock.iloc[:i+1], bench, symbol=symbol,
                                        as_of=str((date + pd.Timedelta(days=4)).date()))
            episode = features.soft_bottoming and not previous
            previous = features.soft_bottoming
            if date < start:
                continue
            record = {"symbol": symbol, "signal_week": str(date.date()),
                      "episode": episode, "features": features.to_dict(),
                      "regime": "above_40w" if bench.close.iloc[-1] >= bench.close.iloc[-40:].mean() else "below_40w",
                      "outcomes": {str(w): measure_outcome(daily[symbol], daily["VOO"], date, w, cutoff)
                                   for w in HORIZONS}}
            records.append(record)
        with (output / "observations.jsonl").open("a") as handle:
            for row in records:
                handle.write(json.dumps(row, allow_nan=False) + "\n")
        rows.extend(records)
        print(f'{number}/{len(symbols)}: {len(records)} eligible weeks, {sum(r["episode"] for r in records)} episodes', flush=True)
    return rows
