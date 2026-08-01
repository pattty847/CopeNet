"""Watchlist-style quote rows served from the durable price cache.

The watchlist panel used to fire one yfinance download per symbol *simultaneously* on
every load — twenty symbols meant twenty concurrent requests in the same instant, and it
repeated on every render rather than once a day. A burst is the traffic shape rate
limiters actually catch; the paced daily universe sweep never was the risk.

Rows now come off the cached daily history, so a warm watchlist costs zero requests. The
cold path stays bounded rather than fanned out, because the first load of a fresh
watchlist is the one moment several symbols legitimately need fetching at once.
"""

from __future__ import annotations

import asyncio
import logging

import pandas as pd

from .data_sources import macro_item_from_frame
from .models import MacroItem
from .price_cache import PriceCache
from .price_history import DAILY, SPLIT_ADJUSTED

#: A watchlist row is a glanceable last price, not a tick feed. Five minutes keeps it
#: honest during market hours while making repeat renders free.
QUOTE_MAX_AGE_SECONDS = 300
#: What `macro_item_from_frame` samples for its sparkline — roughly one trading month.
QUOTE_SPARK_BARS = 22
#: Ceiling on simultaneous cold fetches. Bounded concurrency, not a fan-out.
MAX_CONCURRENT_QUOTE_REFRESHES = 2


def quote_row(
    cache: PriceCache,
    symbol: str,
    *,
    max_age_seconds: float = QUOTE_MAX_AGE_SECONDS,
) -> MacroItem | None:
    """Last price, day change, and sparkline for one symbol. None when it never resolved.

    Deliberately on the stored split-only basis: a watchlist shows the price that actually
    traded. Total-return would leave the last close identical but shift the day-change
    percentage whenever a dividend ex-date falls between the two most recent bars.
    """
    try:
        cache.refresh(symbol, max_age_seconds=max_age_seconds)
    except Exception:
        logging.warning("market quotes: %s price refresh failed", symbol, exc_info=True)
    bars = cache.bars(symbol, timeframe=DAILY, basis=SPLIT_ADJUSTED)
    if len(bars) < 2:
        return None
    window = bars[-QUOTE_SPARK_BARS:]
    return macro_item_from_frame(
        symbol,
        pd.DataFrame({"close": [float(bar.c) for bar in window]}),
    )


async def quote_rows(
    cache: PriceCache,
    symbols: list[str],
    *,
    max_age_seconds: float = QUOTE_MAX_AGE_SECONDS,
) -> dict[str, MacroItem | None]:
    """Quote rows for a whole watchlist, capped at a few concurrent cold fetches."""
    limiter = asyncio.Semaphore(MAX_CONCURRENT_QUOTE_REFRESHES)

    async def _row(symbol: str) -> tuple[str, MacroItem | None]:
        async with limiter:
            item = await asyncio.to_thread(
                quote_row,
                cache,
                symbol,
                max_age_seconds=max_age_seconds,
            )
        return symbol, item

    return dict(await asyncio.gather(*[_row(symbol) for symbol in symbols]))
