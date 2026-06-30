"""Patrick's Market Monitor v1 universe."""

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
    UniverseAsset("ASX", "ASE Technology Holding (ADR)", "holding"),
    UniverseAsset("GOOG", "Alphabet Class C", "holding"),
    UniverseAsset("SOFI", "SoFi Technologies", "holding"),
    UniverseAsset("VTI", "Vanguard Total Stock Market ETF", "holding"),
    UniverseAsset("XLK", "Technology Select Sector SPDR", "holding"),
    UniverseAsset("XLE", "Energy Select Sector SPDR", "holding"),
    UniverseAsset("SLI", "Standard Lithium", "spec"),
    UniverseAsset("VOO", "Vanguard S&P 500 ETF", "index"),
    UniverseAsset("QQQ", "Invesco QQQ Trust", "index"),
    UniverseAsset("VOOG", "Vanguard S&P 500 Growth ETF", "index"),
    UniverseAsset("XLRE", "Real Estate Select Sector SPDR", "sector"),
    UniverseAsset("DXY", "U.S. Dollar Index", "macro", "DX-Y.NYB"),
    UniverseAsset("VIX", "Volatility S&P 500 Index", "macro", "^VIX"),
    UniverseAsset("BTCUSD", "Bitcoin / USD", "macro", "BTC-USD"),
    UniverseAsset("ETHUSD", "Ethereum / USD", "macro", "ETH-USD"),
    UniverseAsset("CRWV", "CoreWeave", "watch"),
    UniverseAsset("SHLD", "Global X Defense Tech ETF", "watch"),
    UniverseAsset("PLD", "Prologis", "watch"),
    UniverseAsset("AMZN", "Amazon", "watch"),
    UniverseAsset("INTC", "Intel", "watch"),
    UniverseAsset("IWM", "iShares Russell 2000 ETF", "watch"),
    UniverseAsset("NVDA", "NVIDIA", "watch"),
    UniverseAsset("TSLA", "Tesla", "watch"),
    UniverseAsset("SPCX", "SpaceX common stock", "watch"),
    UniverseAsset("VONE", "Vanguard Russell 1000 ETF", "index"),
    UniverseAsset("VTHR", "Vanguard Russell 3000 ETF", "index"),
    UniverseAsset("EFA", "iShares MSCI EAFE ETF", "index"),
    UniverseAsset("VWO", "Vanguard FTSE Emerging Markets ETF", "index"),
    UniverseAsset("USO", "United States Oil Fund", "macro"),
    UniverseAsset("SOX", "Philadelphia Semiconductor Index", "sector", "^SOX"),
    UniverseAsset("SMH", "VanEck Semiconductor ETF", "sector"),
    UniverseAsset("XLI", "Industrial Select Sector SPDR", "sector"),
    UniverseAsset("XLF", "Financial Select Sector SPDR", "sector"),
    UniverseAsset("XLP", "Consumer Staples Select Sector SPDR", "sector"),
    UniverseAsset("XLY", "Consumer Discretionary Select Sector SPDR", "sector"),
    UniverseAsset("XLU", "Utilities Select Sector SPDR", "sector"),
    UniverseAsset("XLB", "Materials Select Sector SPDR", "sector"),
    UniverseAsset("XLV", "Health Care Select Sector SPDR", "sector"),
)

PORTFOLIO_BASIS = {
    "ASX": {"shares": 0.0, "avg_cost": 0.0},
    "GOOG": {"shares": 0.0, "avg_cost": 0.0},
    "SOFI": {"shares": 0.0, "avg_cost": 0.0},
    "VTI": {"shares": 0.0, "avg_cost": 0.0},
    "XLK": {"shares": 0.0, "avg_cost": 0.0},
    "XLE": {"shares": 0.0, "avg_cost": 0.0},
    "SLI": {"shares": 0.0, "avg_cost": 0.0},
}

MACRO_SYMBOLS = ("DXY", "VIX", "USO", "BTCUSD", "ETHUSD")
SECTOR_SYMBOLS = ("XLK", "XLE", "XLF", "XLI", "XLV", "XLP", "XLY", "XLU", "XLB", "XLRE", "SMH")


def yf_symbol(symbol: str) -> str:
    normalized = symbol.strip().upper()
    return SYMBOL_MAP.get(normalized, normalized)


def find_asset(symbol: str) -> UniverseAsset | None:
    normalized = symbol.strip().upper()
    for asset in UNIVERSE:
        if asset.symbol == normalized:
            return asset
    return None
