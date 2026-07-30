"""Canonical financial-series boundary shared by UI, RPC, and agent tools."""

from __future__ import annotations

import asyncio
from typing import Any

import pandas as pd

from .data_sources import fetch_ohlcv, fetch_split_history
from .edgar import SEC_API_USER_AGENT
from .sec_fetcher import managed_sec_fetcher


async def get_financial_series(
    *,
    symbol: str,
    metric: str = "revenue",
    frequency: str = "quarterly",
    basis: str = "canonical",
    alignment: str = "availability",
    as_of: str | None = None,
    start: str | None = None,
    end: str | None = None,
    refresh: bool = False,
    include_provenance: bool = True,
) -> dict[str, Any] | None:
    normalized = symbol.strip().upper()
    if not normalized:
        raise ValueError("symbol is required")
    if metric == "trailing_pe":
        return await get_valuation_series(
            symbol=normalized,
            refresh=refresh,
            include_provenance=include_provenance,
        )
    try:
        from copetech_sec import EdgarClient
    except ImportError:
        return None
    async with managed_sec_fetcher(
        EdgarClient,
        user_agent=SEC_API_USER_AGENT,
    ) as client:
        return await client.financials.series(
            normalized,
            metric=metric,
            frequency=frequency,
            basis=basis,
            alignment=alignment,
            as_of=as_of,
            start=start,
            end=end,
            refresh=refresh,
            include_provenance=include_provenance,
        )


async def get_valuation_series(
    *,
    symbol: str,
    refresh: bool = False,
    include_provenance: bool = True,
) -> dict[str, Any] | None:
    """Build canonical P/E from split-adjusted Yahoo prices and point-in-time SEC EPS."""

    normalized = symbol.strip().upper()
    if not normalized:
        raise ValueError("symbol is required")
    try:
        from copetech_sec import EdgarClient
    except ImportError:
        return None
    prices, split_events = await asyncio.to_thread(
        _valuation_price_inputs,
        normalized,
    )
    if not prices:
        return None
    async with managed_sec_fetcher(
        EdgarClient,
        user_agent=SEC_API_USER_AGENT,
    ) as client:
        return await client.financials.valuation(
            normalized,
            price_observations=prices,
            split_events=split_events,
            price_source="yfinance",
            price_basis="split_adjusted",
            refresh=refresh,
            include_provenance=include_provenance,
        )


def _valuation_price_inputs(
    symbol: str,
) -> tuple[list[dict[str, Any]], list[tuple[str, float]] | None]:
    frame = fetch_ohlcv(
        symbol,
        interval="1wk",
        period="10y",
        auto_adjust=True,
    )
    prices: list[dict[str, Any]] = []
    for row in frame.to_dict("records"):
        timestamp = pd.to_datetime(row.get("date"), utc=True, errors="coerce")
        if pd.isna(timestamp):
            continue
        try:
            close = float(row["close"])
        except (KeyError, TypeError, ValueError):
            continue
        prices.append({"time": timestamp.date().isoformat(), "close": close})
    splits, verified = fetch_split_history(symbol)
    return prices, splits if verified else None


def supported_financial_metrics() -> list[dict[str, Any]]:
    try:
        from copetech_sec.financial_metrics import list_supported_metrics
    except ImportError:
        return []
    return list_supported_metrics()
