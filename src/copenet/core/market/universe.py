"""Public, account-neutral Market Monitor universe — the market's plumbing.

Personal holdings and watchlists come from local stores and must never be encoded here.
The split is by ownership, not by importance: everything below is a public instrument that
would be in any operator's dashboard, so it is version-controlled and reviewable. Names that
answer "what do *I* own / follow" live in `watchlist_store` and merge in at runtime via
`merge_watchlist_assets`.

Layers, by the question each answers:

  index     — is the broad market healthy?           VOO, SPY, QQQ, IWM, DIA, RSP, ...
  sector    — where is money rotating?               the 11 SPDR sectors + SMH  (RRG)
  industry  — what fight is happening *underneath*   KRE, XBI, XRT, XHB, ITA    (industry RRG)
              a sector? XLF can look calm while
              regional banks are being dragged.
  macro     — what are rates, credit, vol, FX,       TNX, TLT, IEF, HYG, LQD, UUP, GLD, ...
              and commodities saying?

None of these roles earn per-name signal work (see SIGNAL_ROLES) — they are the context the
signal panels are read against, and putting bonds or gold in an equity breadth reading would
make that number meaningless.
"""

from __future__ import annotations

from .models import UniverseAsset

# CopeNet uses bare, human-readable symbols everywhere (store keys, watchlists, the UI) and
# translates to the provider's convention only at fetch time. Anything needing a caret,
# suffix, or dash belongs here — an unmapped symbol is passed through verbatim, which is why
# a raw "^TNX" or "BTC-USD" in a watchlist would silently create a second, duplicate asset.
SYMBOL_MAP = {
    "DXY": "DX-Y.NYB",
    "VIX": "^VIX",
    "SOX": "^SOX",
    "TNX": "^TNX",  # CBOE 10-year Treasury yield index (quoted as yield x10)
    "BTCUSD": "BTC-USD",
    "ETHUSD": "ETH-USD",
}

UNIVERSE: tuple[UniverseAsset, ...] = (
    # --- index: broad-market health, and the benchmarks everything else is measured against ---
    UniverseAsset("VOO", "Vanguard S&P 500 ETF", "index"),
    UniverseAsset("SPY", "SPDR S&P 500 ETF Trust", "index"),
    UniverseAsset("QQQ", "Invesco QQQ Trust", "index"),
    UniverseAsset("DIA", "SPDR Dow Jones Industrial Average ETF", "index"),
    # Equal-weight S&P: read against VOO it is the cleanest concentration tell there is —
    # when cap-weight runs away from equal-weight, the index is a handful of names.
    UniverseAsset("RSP", "Invesco S&P 500 Equal Weight ETF", "index"),
    UniverseAsset("IWM", "iShares Russell 2000 ETF", "index"),
    UniverseAsset("VONE", "Vanguard Russell 1000 ETF", "index"),
    UniverseAsset("VTHR", "Vanguard Russell 3000 ETF", "index"),
    UniverseAsset("EFA", "iShares MSCI EAFE ETF", "index"),
    UniverseAsset("VWO", "Vanguard FTSE Emerging Markets ETF", "index"),
    # --- sector: the 11 SPDR sectors (all of S&P 500) + semis. Drives the sector RRG. ---
    UniverseAsset("XLK", "Technology Select Sector SPDR", "sector"),
    UniverseAsset("XLC", "Communication Services Select Sector SPDR", "sector"),
    UniverseAsset("XLY", "Consumer Discretionary Select Sector SPDR", "sector"),
    UniverseAsset("XLP", "Consumer Staples Select Sector SPDR", "sector"),
    UniverseAsset("XLE", "Energy Select Sector SPDR", "sector"),
    UniverseAsset("XLF", "Financial Select Sector SPDR", "sector"),
    UniverseAsset("XLV", "Health Care Select Sector SPDR", "sector"),
    UniverseAsset("XLI", "Industrial Select Sector SPDR", "sector"),
    UniverseAsset("XLB", "Materials Select Sector SPDR", "sector"),
    UniverseAsset("XLRE", "Real Estate Select Sector SPDR", "sector"),
    UniverseAsset("XLU", "Utilities Select Sector SPDR", "sector"),
    UniverseAsset("SMH", "VanEck Semiconductor ETF", "sector"),
    UniverseAsset("SOX", "Philadelphia Semiconductor Index", "sector", "^SOX"),
    # --- industry: the fights hiding underneath a sector. Drives the industry RRG. ---
    UniverseAsset("KRE", "SPDR S&P Regional Banking ETF", "industry"),
    UniverseAsset("XBI", "SPDR S&P Biotech ETF", "industry"),
    UniverseAsset("XRT", "SPDR S&P Retail ETF", "industry"),
    UniverseAsset("XHB", "SPDR S&P Homebuilders ETF", "industry"),
    UniverseAsset("ITA", "iShares U.S. Aerospace & Defense ETF", "industry"),
    # --- macro: rates, credit, volatility, currencies, commodities, crypto ---
    UniverseAsset("TNX", "US 10-Year Treasury Yield", "macro", "^TNX"),
    UniverseAsset("TLT", "iShares 20+ Year Treasury Bond ETF", "macro"),
    UniverseAsset("IEF", "iShares 7-10 Year Treasury Bond ETF", "macro"),
    UniverseAsset("HYG", "iShares iBoxx High Yield Corporate Bond ETF", "macro"),
    UniverseAsset("LQD", "iShares iBoxx Investment Grade Corporate Bond ETF", "macro"),
    UniverseAsset("VIX", "Volatility S&P 500 Index", "macro", "^VIX"),
    UniverseAsset("DXY", "U.S. Dollar Index", "macro", "DX-Y.NYB"),
    UniverseAsset("UUP", "Invesco DB US Dollar Index Bullish Fund", "macro"),
    UniverseAsset("GLD", "SPDR Gold Shares", "macro"),
    UniverseAsset("USO", "United States Oil Fund", "macro"),
    UniverseAsset("BTCUSD", "Bitcoin / USD", "macro", "BTC-USD"),
    UniverseAsset("ETHUSD", "Ethereum / USD", "macro", "ETH-USD"),
)

# The macro strip, in reading order: rates → credit → volatility → FX → commodities → crypto.
# HYG/LQD sit together deliberately — high-yield rolling over while investment-grade holds is
# a credit-stress tell that neither ticker shows alone.
MACRO_SYMBOLS = (
    "TNX", "TLT", "IEF",
    "HYG", "LQD",
    "VIX",
    "DXY", "UUP",
    "GLD", "USO",
    "BTCUSD", "ETHUSD",
)
SECTOR_SYMBOLS = ("XLK", "XLE", "XLF", "XLI", "XLV", "XLP", "XLY", "XLU", "XLB", "XLRE", "XLC", "SMH")
# Kept out of SECTOR_SYMBOLS on purpose: research_lab/benchmarks.py maps a stock to its sector
# ETF from that tuple, and an industry fund is not a sector benchmark.
INDUSTRY_SYMBOLS = ("KRE", "XBI", "XRT", "XHB", "ITA")

# Roles that earn a symbol per-name signal work: accumulation, weekly trend changes,
# soft-bottoming, speculative, and the SEC evidence sweep. Index/sector/macro assets are
# context for those panels, not subjects of them.
SIGNAL_ROLES = frozenset({"holding", "watch", "spec"})

# A watchlist with no explicit role is something the operator is watching.
DEFAULT_WATCHLIST_ROLE = "watch"

# Every role a watchlist may carry. "context" is the deliberate opt-out — quoted in the
# watchlist UI, kept out of breadth and the SEC sweep — so it must survive normalization
# rather than being folded into the default the way a typo is.
WATCHLIST_ROLES = SIGNAL_ROLES | {"context"}


def merge_watchlist_assets(lists: list[dict] | None) -> tuple[UniverseAsset, ...]:
    """The scan universe: the public UNIVERSE above plus the operator's own watchlist symbols.

    Personal holdings cannot live in `UNIVERSE` (they are operator data — see fca5acb), but the
    signal panels are defined *over* them, so they have to rejoin the scan at runtime or those
    panels compute over an empty set and silently render empty. Each watchlist carries a `role`
    (default `watch`); every role in `SIGNAL_ROLES` earns per-name signal work.

    UNIVERSE wins on symbol conflict — a sector ETF that also sits in a watchlist stays a
    `sector` asset rather than being duplicated as a holding, so breadth is not double-counted.

    Between watchlists, a signal role beats `context` no matter what order the lists sit in the
    file. `context` is an opt-out, not a claim: a ticker parked in some old broker import must
    not shadow the same ticker in the operator's curated scan list. Ordering decided this before,
    which silently dropped a third of a curated scan on the floor. Within one priority tier the
    first list still wins, so `holding` beats a later `watch` for the same symbol.
    """
    assets = list(UNIVERSE)
    seen = {asset.symbol for asset in assets}
    valid = [wl for wl in (lists or []) if isinstance(wl, dict)]

    def role_of(watchlist: dict) -> str:
        role = str(watchlist.get("role") or DEFAULT_WATCHLIST_ROLE).strip().lower()
        return role if role in WATCHLIST_ROLES else DEFAULT_WATCHLIST_ROLE

    ordered = [wl for wl in valid if role_of(wl) in SIGNAL_ROLES]
    ordered += [wl for wl in valid if role_of(wl) not in SIGNAL_ROLES]

    for watchlist in ordered:
        role = role_of(watchlist)
        for entry in watchlist.get("entries") or []:
            if not isinstance(entry, dict):
                continue
            symbol = str(entry.get("symbol") or "").strip().upper()
            if not symbol or symbol in seen:
                continue
            seen.add(symbol)
            assets.append(UniverseAsset(symbol, str(entry.get("name") or "").strip() or symbol, role))
    return tuple(assets)


def yf_symbol(symbol: str) -> str:
    normalized = symbol.strip().upper()
    return SYMBOL_MAP.get(normalized, normalized)


def find_asset(symbol: str) -> UniverseAsset | None:
    normalized = symbol.strip().upper()
    for asset in UNIVERSE:
        if asset.symbol == normalized:
            return asset
    return None
