"""Offline Stooq end-of-day archive — a wide, shallow companion to the price cache.

The manually downloaded Stooq US archive covers ~13,000 listed tickers back to the
1980s. It answers questions the per-symbol cache cannot afford to: how much of the
market is participating, where strength actually sits. It is deliberately a SEPARATE
store, and these three properties are why:

  1. BASIS. Stooq prices are split AND dividend adjusted — total return, the same
     basis as yfinance's `adj_close`. `price_cache` is split-only by design, because
     a dividend retroactively shifts every prior price and would drift an append-only
     cache at the seam. Writing these bars there under a `split_adjusted` label is
     exactly the silent corruption that cache exists to prevent. Verified against
     cached AAPL: the ratio converges to 1.0000 today and diverges monotonically
     backward, which is dividend adjustment, not a split artifact.

  2. SURVIVORSHIP. Only currently listed tickers are present. SIVB, FRC, TWTR, ATVI
     and BBBY are all absent. That makes the archive USABLE for a present-day
     cross-section — today's breadth denominator is today's listed names, which is
     the correct question — and UNUSABLE for base rates, replay or any historical
     hit-rate work, where the surviving sample overstates returns and understates
     drawdown. `base_rates.py` and `replay.py` must never read from here.

  3. STATIC. This is a snapshot, not a feed. yfinance remains the live edge; the
     archive is refreshed by an occasional manual download.

Total-return basis has one measurable consequence for participation: prices drift up
relative to a price-only moving average, so "above the 200-day" runs slightly high —
and systematically higher in high-yield sectors. Report the basis with the number.
"""

from .store import (
    STOOQ_BASIS,
    StooqArchive,
    StooqUnavailable,
    archive_root,
    load_archive,
)

__all__ = [
    "STOOQ_BASIS",
    "StooqArchive",
    "StooqUnavailable",
    "archive_root",
    "load_archive",
]
