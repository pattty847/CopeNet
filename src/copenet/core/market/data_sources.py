"""Market data adapters for yfinance."""

from __future__ import annotations

from datetime import timezone
from typing import Any
from urllib.request import Request, urlopen
from xml.etree import ElementTree

import pandas as pd

from .models import MacroItem, MarketBar
from .universe import yf_symbol


def fetch_ohlcv(symbol: str, *, interval: str, period: str = "2y", auto_adjust: bool = True) -> pd.DataFrame:
    try:
        import yfinance as yf
    except ImportError as exc:  # pragma: no cover - dependency exists in packaged env
        raise RuntimeError("yfinance is required for market data") from exc
    ticker = yf_symbol(symbol)
    # auto_adjust=True returns split/dividend-adjusted prices. Pattern detection wants split-adjusted
    # shape (returns/drawdowns are scale-invariant to splits); raw prices show fake split gaps.
    # Default is True so every caller — dashboard refresh, chart display, backtester, replay — shares
    # one convention and one MarketStore cache basis. A prior default of False here let the live
    # dashboard/chart paths silently cache unadjusted bars under the same key the backtester and
    # replay.py write split-adjusted bars to, corrupting whichever read second.
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


def fetch_daily_price_history(
    symbol: str,
    *,
    period: str = "max",
) -> tuple[pd.DataFrame, list[tuple[str, float]], list[tuple[str, float]]]:
    """Daily bars on a SPLIT-ONLY basis plus the split and dividend actions, in one request.

    Deliberately NOT `fetch_ohlcv`. That function is pinned to `auto_adjust=True`, which
    folds dividends into the price on top of splits — the right default for the shared
    MarketStore cache, but two different adjustments behind one flag. Yahoo's unadjusted
    `close` column is already split-adjusted on their side, so `auto_adjust=False` is
    precisely how you ask for splits *without* dividends (`adj_close` carries both).

    That distinction is what makes an append-only price cache possible. A dividend
    retroactively shifts every prior dividend-adjusted price, so appending to that basis
    drifts at the seam between old and new rows. Split-only bars move only when a split
    happens. Consumers wanting total return apply the returned dividends themselves via
    `price_history.apply_dividend_adjustment`.

    Returns `(frame, splits, dividends)` where `frame` matches `fetch_ohlcv`'s columns and
    both action lists are `[(iso_date, value)]` oldest-first on that same split basis.
    """
    try:
        import yfinance as yf
    except ImportError as exc:  # pragma: no cover - dependency exists in packaged env
        raise RuntimeError("yfinance is required for market data") from exc
    empty = pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])
    try:
        frame = yf.Ticker(yf_symbol(symbol)).history(
            period=period,
            interval="1d",
            auto_adjust=False,
            actions=True,
        )
    except Exception:
        return empty, [], []
    if frame is None or frame.empty:
        return empty, [], []
    frame = frame.reset_index()
    frame.columns = [str(column).lower() for column in frame.columns]
    if "date" not in frame:
        return empty, [], []
    # `Ticker.history` hands back an exchange-local tz-aware index, unlike `yf.download`'s
    # naive one. Normalize to the calendar trading date so bar timestamps stay identical
    # to every other bar in the system (UTC midnight) rather than shifting by the offset.
    stamps = pd.to_datetime(frame["date"], errors="coerce")
    frame["date"] = pd.to_datetime(
        [stamp.date() if stamp is not pd.NaT else None for stamp in stamps],
        errors="coerce",
    )
    frame = frame.dropna(subset=["date", "close"])
    actions = frame.rename(columns={"stock splits": "splits"})
    splits = _price_actions(actions, "splits")
    dividends = _price_actions(actions, "dividends")
    bars = frame[["date", "open", "high", "low", "close", "volume"]]
    return bars, splits, dividends


def _price_actions(frame: pd.DataFrame, column: str) -> list[tuple[str, float]]:
    if column not in frame:
        return []
    rows = frame[frame[column].fillna(0) > 0]
    return sorted(
        (str(pd.Timestamp(row["date"]).date()), float(row[column]))
        for _, row in rows.iterrows()
    )


def fetch_splits(symbol: str) -> list[tuple[str, float]]:
    """[(ex_date, ratio)] oldest-first — 2.0 is a 2-for-1 forward split, 0.05 a 1-for-20 reverse.

    Deliberately NOT derived from `fetch_ohlcv`: those bars are split-adjusted, so the split is
    exactly what they have erased. Share-count reconstruction (see webull/pnl.py) needs the raw
    corporate action, because a broker's fill history reports quantities as they were on trade day.
    Returns [] for delisted tickers Yahoo no longer serves — callers must handle the gap."""
    events, _verified = fetch_split_history(symbol)
    return events


def fetch_split_history(symbol: str) -> tuple[list[tuple[str, float]], bool]:
    """Return split events plus whether Yahoo successfully verified the history."""
    try:
        import yfinance as yf
    except ImportError as exc:  # pragma: no cover - dependency exists in packaged env
        raise RuntimeError("yfinance is required for market data") from exc
    try:
        series = yf.Ticker(yf_symbol(symbol)).splits
    except Exception:
        return [], False
    if series is None or len(series) == 0:
        return [], True
    return (
        sorted(
            (str(stamp.date()), float(ratio))
            for stamp, ratio in series.items()
            if ratio
        ),
        True,
    )


TREASURY_YIELD_CURVE_URL = (
    "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml"
    "?data=daily_treasury_yield_curve&field_tdr_date_value={year}"
)


def fetch_treasury_par_yield_history(year: int) -> pd.DataFrame:
    """Official daily Constant Maturity Treasury par yields for one calendar year."""
    request = Request(
        TREASURY_YIELD_CURVE_URL.format(year=year),
        headers={"User-Agent": "CopeNet/0.1 Treasury curve"},
    )
    try:
        with urlopen(request, timeout=20) as response:
            payload = response.read()
    except OSError as exc:
        raise RuntimeError(f"U.S. Treasury yield-curve feed unavailable for {year}: {exc}") from exc
    try:
        return parse_treasury_par_yield_xml(payload)
    except ElementTree.ParseError as exc:
        raise RuntimeError("U.S. Treasury returned malformed yield-curve XML") from exc


def parse_treasury_par_yield_xml(payload: bytes) -> pd.DataFrame:
    """Normalize the Treasury Atom/XML feed at its external-data trust boundary."""
    root = ElementTree.fromstring(payload)
    namespaces = {
        "m": "http://schemas.microsoft.com/ado/2007/08/dataservices/metadata",
        "d": "http://schemas.microsoft.com/ado/2007/08/dataservices",
    }
    rows: list[dict[str, Any]] = []
    for properties in root.findall(".//m:properties", namespaces):
        raw_date = properties.findtext("d:NEW_DATE", namespaces=namespaces)
        if not raw_date:
            continue
        row: dict[str, Any] = {"date": raw_date}
        for element in list(properties):
            field = element.tag.rsplit("}", 1)[-1]
            if not field.startswith("BC_") or field.endswith("DISPLAY") or not element.text:
                continue
            try:
                row[field] = float(element.text)
            except ValueError:
                continue
        rows.append(row)
    if not rows:
        return pd.DataFrame()
    frame = pd.DataFrame(rows)
    frame["date"] = pd.to_datetime(frame["date"], utc=True, errors="coerce")
    return frame.dropna(subset=["date"]).drop_duplicates("date", keep="last").sort_values("date").set_index("date")


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


def fetch_quote_row(symbol: str) -> MacroItem | None:
    """Lightweight last-price + day-change + sparkline for one symbol, e.g. for a watchlist
    row. Reuses the same split-adjusted fetch_ohlcv pipeline as every other Market Monitor
    consumer but with a short period — a watchlist row only needs
    recent context, not the 2y default. Deliberately NOT written to MarketStore's bar cache
    (see the auto_adjust invariant in AGENTS.md): this is a small, on-demand, ad hoc read, not
    part of the shared (symbol, timeframe) cache basis every other caller relies on."""
    frame = fetch_ohlcv(symbol, interval="1d", period="1mo", auto_adjust=True)
    return macro_item_from_frame(symbol, frame)


def search_symbols(query: str, *, limit: int = 8) -> list[dict[str, str]]:
    """Live ticker lookup by symbol or company name via Yahoo's search endpoint (yfinance.Search).
    Best-effort: any failure returns an empty list rather than raising, since this backs an
    interactive typeahead, not a data pipeline."""
    normalized = (query or "").strip()
    if not normalized:
        return []
    try:
        import yfinance as yf

        quotes = yf.Search(normalized, max_results=limit).quotes
    except Exception:
        return []
    results: list[dict[str, str]] = []
    seen: set[str] = set()
    for quote in quotes or []:
        if not isinstance(quote, dict):
            continue
        symbol = str(quote.get("symbol") or "").strip()
        quote_type = str(quote.get("quoteType") or "").upper()
        if not symbol or symbol in seen or quote_type not in {"EQUITY", "ETF", "INDEX", "CRYPTOCURRENCY"}:
            continue
        seen.add(symbol)
        results.append(
            {
                "symbol": symbol,
                "name": str(quote.get("longname") or quote.get("shortname") or symbol),
                "exchange": str(quote.get("exchDisp") or quote.get("exchange") or ""),
            }
        )
        if len(results) >= limit:
            break
    return results


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


def fetch_key_stats(symbol: str) -> dict[str, Any] | None:
    """Headline stats from yfinance fast_info — market cap, 52-week range, average volume —
    for the ticker page's Signal Readout. Tolerant by design: returns None on any failure or
    when nothing resolves (index/ETF symbols may lack a market cap), and callers treat None
    as "unavailable" rather than zero."""
    try:
        import yfinance as yf
    except ImportError:
        return None
    try:
        info = yf.Ticker(yf_symbol(symbol)).fast_info
        stats = {
            "market_cap": _fast_info_number(info, "market_cap"),
            "year_high": _fast_info_number(info, "year_high"),
            "year_low": _fast_info_number(info, "year_low"),
            "avg_volume_3m": _fast_info_number(info, "three_month_average_volume"),
        }
    except Exception:
        return None
    return stats if any(value is not None for value in stats.values()) else None


def _fast_info_number(info: Any, attr: str) -> float | None:
    try:
        value = getattr(info, attr)
    except Exception:
        return None
    return float(value) if isinstance(value, (int, float)) else None
