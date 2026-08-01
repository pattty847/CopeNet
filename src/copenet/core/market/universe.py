"""Public, account-neutral Market Monitor universe.

Personal holdings and watchlists come from local stores and must never be encoded here.
"""

from __future__ import annotations

from .models import UniverseAsset

SYMBOL_MAP = {
    "DXY": "DX-Y.NYB",
    "VIX": "^VIX",
    "SOX": "^SOX",
    "BTCUSD": "BTC-USD",
    "ETHUSD": "ETH-USD",
}

UNIVERSE: tuple[UniverseAsset, ...] = (
    UniverseAsset("VOO", "Vanguard S&P 500 ETF", "index"),
    UniverseAsset("QQQ", "Invesco QQQ Trust", "index"),
    UniverseAsset("IWM", "iShares Russell 2000 ETF", "index"),
    UniverseAsset("VTHR", "Vanguard Russell 3000 ETF", "index"),
    UniverseAsset("EFA", "iShares MSCI EAFE ETF", "index"),
    UniverseAsset("VWO", "Vanguard FTSE Emerging Markets ETF", "index"),
    UniverseAsset("XLRE", "Real Estate Select Sector SPDR", "sector"),
    UniverseAsset("DXY", "U.S. Dollar Index", "macro", "DX-Y.NYB"),
    UniverseAsset("VIX", "Volatility S&P 500 Index", "macro", "^VIX"),
    UniverseAsset("BTCUSD", "Bitcoin / USD", "macro", "BTC-USD"),
    UniverseAsset("ETHUSD", "Ethereum / USD", "macro", "ETH-USD"),
    UniverseAsset("VONE", "Vanguard Russell 1000 ETF", "index"),
    UniverseAsset("USO", "United States Oil Fund", "macro"),
    UniverseAsset("SOX", "Philadelphia Semiconductor Index", "sector", "^SOX"),
    UniverseAsset("SMH", "VanEck Semiconductor ETF", "sector"),
    UniverseAsset("XLK", "Technology Select Sector SPDR", "sector"),
    UniverseAsset("XLE", "Energy Select Sector SPDR", "sector"),
    UniverseAsset("XLI", "Industrial Select Sector SPDR", "sector"),
    UniverseAsset("XLF", "Financial Select Sector SPDR", "sector"),
    UniverseAsset("XLP", "Consumer Staples Select Sector SPDR", "sector"),
    UniverseAsset("XLY", "Consumer Discretionary Select Sector SPDR", "sector"),
    UniverseAsset("XLU", "Utilities Select Sector SPDR", "sector"),
    UniverseAsset("XLB", "Materials Select Sector SPDR", "sector"),
    UniverseAsset("XLV", "Health Care Select Sector SPDR", "sector"),
    UniverseAsset("XLC", "Communication Services Select Sector SPDR", "sector"),
)

MACRO_SYMBOLS = ("DXY", "VIX", "USO", "BTCUSD", "ETHUSD")
SECTOR_SYMBOLS = ("XLK", "XLE", "XLF", "XLI", "XLV", "XLP", "XLY", "XLU", "XLB", "XLRE", "XLC", "SMH")


def yf_symbol(symbol: str) -> str:
    normalized = symbol.strip().upper()
    return SYMBOL_MAP.get(normalized, normalized)


def find_asset(symbol: str) -> UniverseAsset | None:
    normalized = symbol.strip().upper()
    for asset in UNIVERSE:
        if asset.symbol == normalized:
            return asset
    return None
