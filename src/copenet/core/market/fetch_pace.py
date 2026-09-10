"""How fast CopeNet is allowed to ask yfinance for anything.

One home, because two lanes now share the budget: the daily sweep walks the watchlist, and
the intraday lane pages 1m history. Yahoo counts requests per caller, not per feature, so a
second copy of this number would be two lanes each politely observing half a policy.

The SEC lane has its own pace in `sec_fetcher.py` — a different vendor with a different,
published limit. Same idea, deliberately not the same number.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

DEFAULT_MARKET_FETCH_PACE = 0.2


def market_fetch_pace() -> float:
    """Seconds between yfinance requests.

    Read at call time, never at import: `copenet._env` loads `.env` inside `main()`, after
    the import chain has already run, so a module-level read would resolve before the
    operator's configuration existed.
    """
    raw = os.environ.get("COPNET_MARKET_FETCH_PACE", "").strip()
    if not raw:
        return DEFAULT_MARKET_FETCH_PACE
    try:
        return max(float(raw), 0.0)
    except ValueError:
        logger.warning(
            "COPNET_MARKET_FETCH_PACE=%r is not a number — using the default %.2fs.",
            raw, DEFAULT_MARKET_FETCH_PACE,
        )
        return DEFAULT_MARKET_FETCH_PACE
