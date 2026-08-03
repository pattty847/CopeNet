"""Canonical financial-series boundary shared by UI, RPC, and agent tools."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from copenet._paths import default_sessions_dir

from .data_sources import fetch_split_history
from .edgar import SEC_API_USER_AGENT
from .price_cache import PriceCache
from .price_history import SPLIT_ADJUSTED, WEEKLY, bar_date
from .sec_fetcher import managed_sec_fetcher


def default_market_dir() -> Path:
    """Local copy of the runtime's market root — importing `runtime` here would cycle."""
    return default_sessions_dir().parent / "market"


def _edgar_cache_dir() -> str:
    """Pin the SEC fact ledger under the market root instead of the process CWD."""
    return str(default_market_dir() / "edgar")


# Metrics whose numerator is a market price rather than a filed fact. They need
# the price cache and the valuation engine instead of the plain series path.
VALUATION_METRICS = frozenset({"trailing_pe"})


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
    if metric in VALUATION_METRICS:
        return await get_valuation_series(
            symbol=normalized,
            metric=metric,
            as_of=as_of,
            refresh=refresh,
            include_provenance=include_provenance,
        )
    try:
        from copetech_sec import EdgarClient
    except ImportError:
        return None
    split_events = None
    if metric == "diluted_eps" and frequency == "ttm":
        splits, verified = await asyncio.to_thread(fetch_split_history, normalized)
        split_events = splits if verified else None
    async with managed_sec_fetcher(
        EdgarClient,
        user_agent=SEC_API_USER_AGENT,
        cache_dir=_edgar_cache_dir(),
    ) as client:
        payload = await client.financials.series(
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
            split_events=split_events,
        )
    filtered = _point_in_time_financial_payload(payload, as_of=as_of)
    if filtered is not None:
        filtered["kind"] = "financial"
    return filtered


async def get_valuation_series(
    *,
    symbol: str,
    metric: str = "trailing_pe",
    as_of: str | None = None,
    refresh: bool = False,
    include_provenance: bool = True,
) -> dict[str, Any] | None:
    """Build canonical P/E from split-adjusted Yahoo prices and point-in-time SEC EPS."""

    normalized = symbol.strip().upper()
    if not normalized:
        raise ValueError("symbol is required")
    if metric != "trailing_pe":
        raise ValueError(f"unsupported valuation metric {metric!r}")
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
        cache_dir=_edgar_cache_dir(),
    ) as client:
        payload = await client.financials.valuation(
            normalized,
            price_observations=prices,
            split_events=split_events,
            price_source="yfinance",
            price_basis="split_adjusted",
            refresh=refresh,
            include_provenance=include_provenance,
        )
    filtered = _point_in_time_valuation_payload(
        _trim_leading_unpriced(payload), as_of=as_of
    )
    if filtered is not None:
        filtered["kind"] = "valuation"
    return filtered


def _trim_leading_unpriced(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    """Drop leading rows from before any SEC earnings existed.

    Price history now reaches back decades further than XBRL does — KO's candles start in
    1962 against Company Facts from roughly 2009 — so the head of the series is thousands
    of rows that can never carry a ratio. Gaps *within* the covered range stay: those mean
    "stale or non-positive earnings", which is information. A leading run of nothing is not.
    """
    if payload is None:
        return None
    observations = payload.get("observations")
    if not isinstance(observations, list):
        return payload
    first_priced = next(
        (
            index
            for index, observation in enumerate(observations)
            if isinstance(observation, dict) and observation.get("epsAvailableAt")
        ),
        None,
    )
    if first_priced is None or first_priced == 0:
        return payload
    trimmed = dict(payload)
    trimmed["observations"] = observations[first_priced:]
    return trimmed


def _point_in_time_financial_payload(
    payload: dict[str, Any] | None,
    *,
    as_of: str | None,
) -> dict[str, Any] | None:
    """Defensively enforce availableAt <= as_of at the external-data boundary."""
    return _filter_observations(
        payload,
        as_of=as_of,
        is_eligible=_financial_observation_is_eligible,
    )


def _point_in_time_valuation_payload(
    payload: dict[str, Any] | None,
    *,
    as_of: str | None,
) -> dict[str, Any] | None:
    """Bound valuation rows by price time and reject future EPS provenance."""
    return _filter_observations(
        payload,
        as_of=as_of,
        is_eligible=_valuation_observation_is_eligible,
    )


def _filter_observations(
    payload: dict[str, Any] | None,
    *,
    as_of: str | None,
    is_eligible: Callable[[Any, pd.Timestamp], bool],
) -> dict[str, Any] | None:
    if payload is None or as_of is None:
        return payload
    cutoff = pd.to_datetime(as_of, utc=True, errors="coerce")
    if pd.isna(cutoff):
        raise ValueError(f"invalid as_of timestamp: {as_of!r}")
    observations = payload.get("observations")
    if not isinstance(observations, list):
        return payload
    filtered = deepcopy(payload)
    filtered["observations"] = [
        observation
        for observation in filtered["observations"]
        if is_eligible(observation, cutoff)
    ]
    filtered["asOf"] = as_of
    return filtered


def _financial_observation_is_eligible(observation: Any, cutoff: pd.Timestamp) -> bool:
    if not isinstance(observation, dict):
        return False
    available_at = pd.to_datetime(
        observation.get("availableAt"),
        utc=True,
        errors="coerce",
    )
    return not pd.isna(available_at) and available_at <= cutoff


def _valuation_observation_is_eligible(observation: Any, cutoff: pd.Timestamp) -> bool:
    if not isinstance(observation, dict):
        return False
    timestamp = pd.to_datetime(
        observation.get("timestamp"),
        utc=True,
        errors="coerce",
    )
    if pd.isna(timestamp) or timestamp > cutoff:
        return False
    raw_eps_available_at = observation.get("epsAvailableAt")
    if raw_eps_available_at is None:
        return True
    eps_available_at = pd.to_datetime(
        raw_eps_available_at,
        utc=True,
        errors="coerce",
    )
    return not pd.isna(eps_available_at) and eps_available_at <= timestamp


def _valuation_price_inputs(
    symbol: str,
    *,
    prices_cache: PriceCache | None = None,
) -> tuple[list[dict[str, Any]], list[tuple[str, float]] | None]:
    """Weekly closes on a SPLIT-ONLY basis, plus the split history, for trailing P/E.

    P/E is price paid per dollar of earnings, so the numerator must be the price that
    actually traded — split-adjusted, because a split is mechanical, but *not* dividend
    adjusted. This previously read `auto_adjust=True`, which folds dividends in on top of
    splits and quietly back-shifts every historical price downward. Same EPS over a lower
    price reads as a lower multiple, so historical P/E was understated by an amount that
    grew with lookback and with dividend yield (measured at the 10-year mark: XOM 35%,
    KO 27%, AAPL 8%), decaying to zero at the right edge — the shape of a de-rating that
    never happened.

    The price cache already stores exactly this basis, so it is also the fetch-free path.
    """
    cache = prices_cache or PriceCache(default_market_dir() / "prices")
    cache.refresh(symbol)
    bars = cache.bars(symbol, timeframe=WEEKLY, basis=SPLIT_ADJUSTED)
    prices = [
        {"time": bar_date(bar).isoformat(), "close": float(bar.c)}
        for bar in bars
        if float(bar.c) > 0
    ]
    history = cache.load(symbol)
    if history is not None:
        return prices, history.splits
    splits, verified = fetch_split_history(symbol)
    return prices, splits if verified else None


def supported_financial_metrics() -> list[dict[str, Any]]:
    """Base and derived SEC metrics plus CopeNet's own price-backed valuation metrics."""
    try:
        from copetech_sec.financial_series_service import FinancialSeriesService
    except ImportError:
        return []
    return FinancialSeriesService.supported_metrics() + [
        {
            "id": "trailing_pe",
            "label": "Trailing P/E",
            "factType": "valuation",
            "validUnits": ["ratio"],
            "aggregation": "composite",
            "derived": True,
            "components": ["diluted_eps", "price"],
        }
    ]
