"""Watchlist RPC handlers — Patrick's user-curated add/remove ticker list, distinct from the
fixed dashboard UNIVERSE (core/market/universe.py) that drives the always-on panels."""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable

from copenet.core.market.data_sources import fetch_quote_row, search_symbols
from copenet.core.market.runtime import default_market_dir
from copenet.core.market.store import MarketStore
from copenet.core.market.universe import find_asset
from copenet.core.market.watchlist_store import WatchlistStore
from copenet.host.rpc_schema import ResponseFrame, make_response_frame

SendJson = Callable[[dict[str, Any]], Awaitable[None]]


def _store(orchestrator) -> WatchlistStore:
    """Same lazy-singleton-on-orchestrator pattern as rpc_market.py's _runtime(). The path is
    derived from orchestrator.market_store's root (not a bare default_market_dir() call) so
    tests that scope `market_store` to tmp_path automatically scope the watchlist file too —
    otherwise a FakeOrchestrator without `_market_watchlist_store` set would silently write to
    the real ~/.copenet market dir instead of the test's tmp_path."""
    store = getattr(orchestrator, "_market_watchlist_store", None)
    if isinstance(store, WatchlistStore):
        return store
    market_store = getattr(orchestrator, "market_store", None)
    root = market_store.root_dir if isinstance(market_store, MarketStore) else default_market_dir()
    store = WatchlistStore(root / "watchlist.json")
    try:
        setattr(orchestrator, "_market_watchlist_store", store)
    except Exception:
        pass
    return store


async def _quote_items(entries: list[dict[str, str]]) -> list[dict[str, Any]]:
    async def _row(entry: dict[str, str]) -> dict[str, Any]:
        symbol = entry["symbol"]
        item = await asyncio.to_thread(fetch_quote_row, symbol)
        asset = find_asset(symbol)
        name = entry.get("name") or (asset.name if asset else "") or symbol
        if item is None:
            return {"symbol": symbol, "name": name, "value": "—", "change": "—", "tone": "flat", "spark": []}
        return {"symbol": symbol, "name": name, "value": item.value, "change": item.change, "tone": item.tone, "spark": item.spark}

    return list(await asyncio.gather(*[_row(e) for e in entries]))


async def handle_market_watchlist_get(request_id: str, params: dict[str, Any] | None, send_json: SendJson, orchestrator) -> None:
    del params
    items = await _quote_items(_store(orchestrator).list())
    await send_json(make_response_frame(ResponseFrame(id=request_id, ok=True, payload={"items": items})))


async def handle_market_watchlist_add(request_id: str, params: dict[str, Any] | None, send_json: SendJson, orchestrator) -> None:
    raw = params or {}
    symbol = str(raw.get("symbol") or "").strip().upper()
    name = str(raw.get("name") or "").strip()
    if not symbol:
        raise ValueError("symbol is required")
    probe = await asyncio.to_thread(fetch_quote_row, symbol)
    if probe is None:
        raise ValueError(f"'{symbol}' did not resolve to a tradable ticker")
    entries = _store(orchestrator).add(symbol, name)
    items = await _quote_items(entries)
    await send_json(make_response_frame(ResponseFrame(id=request_id, ok=True, payload={"items": items})))


async def handle_market_watchlist_remove(request_id: str, params: dict[str, Any] | None, send_json: SendJson, orchestrator) -> None:
    raw = params or {}
    symbol = str(raw.get("symbol") or "").strip().upper()
    if not symbol:
        raise ValueError("symbol is required")
    entries = _store(orchestrator).remove(symbol)
    items = await _quote_items(entries)
    await send_json(make_response_frame(ResponseFrame(id=request_id, ok=True, payload={"items": items})))


async def handle_market_symbols_search(request_id: str, params: dict[str, Any] | None, send_json: SendJson, orchestrator) -> None:
    del orchestrator
    raw = params or {}
    query = str(raw.get("query") or "").strip()
    raw_limit = raw.get("limit")
    try:
        limit = max(1, min(int(raw_limit), 15)) if raw_limit is not None else 8
    except (TypeError, ValueError):
        limit = 8
    results = await asyncio.to_thread(search_symbols, query, limit=limit)
    await send_json(make_response_frame(ResponseFrame(id=request_id, ok=True, payload={"results": results})))
