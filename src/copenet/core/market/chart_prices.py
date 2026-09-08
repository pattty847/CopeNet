"""One immutable cache revision supplies chart timeframes and completion provenance."""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import logging

from .alert_candles import completed_candles
from .alert_rules import supported_symbol
from .chart_workspace.codec import digest
from .price_history import chart_history_window, split_fingerprint


def candle_hash(rows: list[dict]) -> str:
    # Browser JSON serializes integral prices as integers. Normalize only the numeric
    # representation so both sides hash the exact same OHLCV values.
    return digest([{**{key: float(row[key]) for key in ('o', 'h', 'l', 'c')},
                    't': int(row['t']), 'v': int(row['v'])} for row in rows])


def chart_price_snapshot(runtime, symbol: str, *, now: datetime | None = None) -> tuple[dict, dict | None]:
    now = now or datetime.now(timezone.utc)
    try:
        runtime.prices.refresh(symbol)
    except Exception:
        logging.warning('market: %s price cache refresh failed', symbol, exc_info=True)
    try:
        history = runtime.prices.load(symbol)
    except Exception:
        logging.warning('market: %s price cache read failed', symbol, exc_info=True)
        history = None
    if history is None:
        return {frame: runtime.store.load_bars(symbol, frame) for frame in ('daily', 'weekly', 'monthly')}, None
    series = {frame: chart_history_window(history.derive(timeframe=frame), frame) for frame in ('daily', 'weekly', 'monthly')}
    completion = completed_candles(history, 'daily', now) if supported_symbol(symbol) else None
    provenance = {'symbol': symbol, 'basis': 'split_adjusted', 'calendar': 'XNYS' if completion else None,
                  'splits': history.splits, 'splitFingerprint': split_fingerprint(history.splits),
                  'updatedAt': history.updated_at, 'candleHash': candle_hash([asdict(bar) for bar in series['daily']]),
                  'completionStatus': completion.status if completion else 'unsupported',
                  'completedThrough': completion.bars[-1].t if completion and completion.bars else None,
                  'completedCloseAt': completion.close_times[completion.bars[-1].t] if completion and completion.bars else None}
    return series, provenance
