"""Market data adapters for yfinance."""

from __future__ import annotations

from datetime import timezone
from typing import Any

import pandas as pd

from .models import MacroItem, MarketBar
from .universe import yf_symbol


def fetch_ohlcv(symbol: str, *, interval: str, period: str = "2y", auto_adjust: bool = False) -> pd.DataFrame:
    try:
        import yfinance as yf
    except ImportError as exc:  # pragma: no cover - dependency exists in packaged env
        raise RuntimeError("yfinance is required for market data") from exc
    ticker = yf_symbol(symbol)
    # auto_adjust=True returns split/dividend-adjusted prices. Pattern detection wants split-adjusted
    # shape (returns/drawdowns are scale-invariant to splits); raw prices show fake split gaps.
    frame = yf.download(ticker, period=period, interval=interval, auto_adjust=auto_adjust, progress=False, threads=False)
    if frame is None or frame.empty:
        return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])
    if isinstance(frame.columns, pd.MultiIndex):
        frame.columns = [str(col[0]).lower() for col in frame.columns]
    else:
        frame.columns = [str(col).lower() for col in frame.columns]
    frame = frame.reset_index()
    frame.columns = [str(column).lower() for column in frame.columns]
    frame = frame.rename(columns={"datetime": "date", "adj close": "adj_close"})
    if "close" not in frame and "adj_close" in frame:
        frame["close"] = frame["adj_close"]
    return frame[["date", "open", "high", "low", "close", "volume"]].dropna(subset=["close"])


def frame_to_bars(frame: pd.DataFrame) -> list[MarketBar]:
    bars: list[MarketBar] = []
    if frame.empty:
        return bars
    for row in frame.to_dict("records"):
        dt = pd.to_datetime(row["date"], utc=True).to_pydatetime().astimezone(timezone.utc)
        bars.append(
            MarketBar(
                t=int(dt.timestamp()),
                o=round(float(row.get("open") or row.get("close") or 0), 4),
                h=round(float(row.get("high") or row.get("close") or 0), 4),
                l=round(float(row.get("low") or row.get("close") or 0), 4),
                c=round(float(row.get("close") or 0), 4),
                v=int(float(row.get("volume") or 0)),
            )
        )
    return bars


def fetch_fund_profile(symbol: str) -> dict[str, Any] | None:
    """Best-effort ETF/fund exposure via yfinance (`funds_data`). Individual stocks and any lookup
    failure return None — there is no fallback data source, so callers must treat this as optional.
    """
    try:
        import yfinance as yf

        funds_data = yf.Ticker(yf_symbol(symbol)).funds_data
        top_holdings = funds_data.top_holdings
        sector_weightings = funds_data.sector_weightings
    except Exception:
        return None
    holdings: list[dict[str, Any]] = []
    if top_holdings is not None and not top_holdings.empty:
        for row_symbol, row in top_holdings.reset_index().iterrows():
            del row_symbol
            symbol_col = row.iloc[0]
            name = row.get("Name")
            weight = row.get("Holding Percent")
            holdings.append(
                {
                    "symbol": str(symbol_col),
                    "name": str(name) if name is not None else None,
                    "weightPct": round(float(weight) * 100, 2) if weight is not None else None,
                }
            )
    sectors = {}
    if isinstance(sector_weightings, dict):
        sectors = {
            str(key): round(float(value) * 100, 1)
            for key, value in sector_weightings.items()
            if isinstance(value, (int, float)) and value
        }
    if not holdings and not sectors:
        return None
    return {"source": "yfinance", "topHoldings": holdings, "sectorWeightPct": sectors}


def macro_item_from_frame(label: str, frame: pd.DataFrame) -> MacroItem | None:
    if frame.empty or len(frame) < 2:
        return None
    close = frame["close"].astype(float).dropna()
    if len(close) < 2:
        return None
    last = float(close.iloc[-1])
    previous = float(close.iloc[-2])
    pct = ((last / previous) - 1) * 100 if previous else 0.0
    tone = "up" if pct > 0 else "down" if pct < 0 else "flat"
    return MacroItem(
        label=label,
        value=_format_value(label, last),
        change=f"{pct:+.2f}%",
        tone=tone,
        spark=[round(float(item), 4) for item in close.tail(22).tolist()],
    )


def _format_value(label: str, value: float) -> str:
    if label == "VIX":
        return f"{value:.1f}"
    if label in {"BTCUSD", "ETHUSD"}:
        return f"${value:,.0f}"
    if label == "DXY":
        return f"{value:.2f}"
    return f"${value:,.2f}"
