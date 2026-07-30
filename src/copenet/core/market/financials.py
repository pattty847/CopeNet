"""Canonical financial-series boundary shared by UI, RPC, and agent tools."""

from __future__ import annotations

from typing import Any

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
    try:
        from copetech_sec import SECDataFetcher
    except ImportError:
        return None
    async with managed_sec_fetcher(
        SECDataFetcher,
        user_agent=SEC_API_USER_AGENT,
    ) as fetcher:
        return await fetcher.get_financial_series(
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


def supported_financial_metrics() -> list[dict[str, Any]]:
    try:
        from copetech_sec.financial_metrics import list_supported_metrics
    except ImportError:
        return []
    return list_supported_metrics()
