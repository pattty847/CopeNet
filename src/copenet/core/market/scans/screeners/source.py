"""Pinned tvscreener adapter; vendor names and missing values normalize only here."""
from __future__ import annotations

import math
import re
from numbers import Real
from tvscreener import Market, StockField as F, StockScreener
from .models import MAX_ROWS, ScreenerConfig

FIELDS = {
    "name": F.DESCRIPTION, "sector": F.SECTOR, "type": F.TYPE, "subtype": F.SUBTYPE,
    "price": F.PRICE, "change": F.CHANGE_PERCENT, "marketCap": F.MARKET_CAPITALIZATION,
    "averageVolume": F.AVERAGE_VOLUME_30_DAY, "relativeVolume": F.RELATIVE_VOLUME,
    "rsi": F.RELATIVE_STRENGTH_INDEX_14, "sma50": F.SIMPLE_MOVING_AVERAGE_50,
    "sma200": F.SIMPLE_MOVING_AVERAGE_200, "high52": F.WEEK_HIGH_52,
    "monthReturn": F.MONTHLY_PERFORMANCE, "bandUpper": F.BOLLINGER_UPPER_BAND_20,
    "bandLower": F.BOLLINGER_LOWER_BAND_20,
}
TEXT_FIELDS = {"name", "sector", "type", "subtype"}


def number(value):
    return float(value) if isinstance(value, Real) and not isinstance(value, bool) and math.isfinite(value) else None


def normalize(raw: dict) -> dict | None:
    identifier = raw.get("Symbol")
    if not isinstance(identifier, str) or not re.fullmatch(r"(?:NASDAQ|NYSE|AMEX):[A-Z][A-Z0-9.\-]{0,14}", identifier):
        return None
    exchange, symbol = identifier.split(":")
    row = {"id": identifier, "symbol": symbol.replace(".", "-"), "exchange": exchange}
    for key, field in FIELDS.items():
        value = raw.get(field.value[0])
        row[key] = value if key in TEXT_FIELDS and isinstance(value, str) else None if key in TEXT_FIELDS else number(value)
    mode = raw.get("Update Mode")
    row["updateMode"] = mode if isinstance(mode, str) else "unknown"
    return row


def fetch_snapshot(config: ScreenerConfig) -> dict:
    query = StockScreener()
    query.set_markets(Market.AMERICA)
    query.select(*FIELDS.values())
    query.where(F.TYPE == "stock").where(F.SUBTYPE == "common").where(F.EXCHANGE.isin(["NASDAQ", "NYSE", "AMEX"]))
    cap_filter = F.MARKET_CAPITALIZATION >= config.minCap if config.maxCap is None else F.MARKET_CAPITALIZATION.between(config.minCap, config.maxCap)
    query.where(cap_filter).where(F.PRICE >= config.minPrice)
    # One bounded response avoids a moving pagination window; the extra row detects truncation.
    query.sort_by(F.MARKET_CAPITALIZATION, ascending=False)
    query.set_range(0, MAX_ROWS + 1)
    try:
        frame = query.get()
    except Exception as exc:
        raise ValueError("TradingView screening is unavailable. Retry later; the previous snapshot is retained.") from exc
    required = {"Symbol", *(field.value[0] for field in FIELDS.values())}
    if not required.issubset(frame.columns):
        raise ValueError("TradingView returned an unexpected field schema; the previous snapshot is retained")
    records = frame.to_dict("records")
    rows = [row for raw in records[:MAX_ROWS] if (row := normalize(raw)) is not None]
    if len({row["id"] for row in rows}) != len(rows):
        raise ValueError("TradingView returned duplicate instruments; retry the screen")
    return {"rows": rows, "received": len(records), "invalid": min(len(records), MAX_ROWS) - len(rows),
            "truncated": len(records) > MAX_ROWS}
