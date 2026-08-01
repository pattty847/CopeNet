"""Watchlist RPC handlers — the operator's user-curated add/remove ticker list, distinct from the
fixed dashboard UNIVERSE (core/market/universe.py) that drives the always-on panels."""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable

from copenet.core.market.data_sources import search_symbols
from copenet.core.market.price_cache import PriceCache
from copenet.core.market.quotes import quote_row, quote_rows
from copenet.core.market.runtime import default_market_dir
from copenet.core.market.store import MarketStore
from copenet.core.market.universe import find_asset
from copenet.core.market.watchlist_store import WatchlistStore
from copenet.host.rpc_schema import ResponseFrame, make_response_frame

SendJson = Callable[[dict[str, Any]], Awaitable[None]]


def price_cache(orchestrator) -> PriceCache:
    """Shared price cache, rooted off the same market dir as `watchlist_store`.

    Deriving the root from `orchestrator.market_store` rather than calling
    `default_market_dir()` keeps tests that scope the store to tmp_path from writing into
    the real ~/.copenet market dir — same reasoning as `watchlist_store` below.
    """
    cache = getattr(orchestrator, "_market_price_cache", None)
    if isinstance(cache, PriceCache):
        return cache
    market_store = getattr(orchestrator, "market_store", None)
    root = market_store.root_dir if isinstance(market_store, MarketStore) else default_market_dir()
    cache = PriceCache(root / "prices")
    try:
        setattr(orchestrator, "_market_price_cache", cache)
    except Exception:
        pass
    return cache


def watchlist_store(orchestrator) -> WatchlistStore:
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


async def _quote_items(entries: list[dict[str, str]], cache: PriceCache) -> list[dict[str, Any]]:
    quotes = await quote_rows(cache, [entry["symbol"] for entry in entries])
    items: list[dict[str, Any]] = []
    for entry in entries:
        symbol = entry["symbol"]
        asset = find_asset(symbol)
        name = entry.get("name") or (asset.name if asset else "") or symbol
        item = quotes.get(symbol)
        if item is None:
            items.append({"symbol": symbol, "name": name, "value": "—", "change": "—", "tone": "flat", "spark": []})
            continue
        items.append({"symbol": symbol, "name": name, "value": item.value, "change": item.change, "tone": item.tone, "spark": item.spark})
    return items


async def _state_payload(store: WatchlistStore, cache: PriceCache) -> dict[str, Any]:
    """Full watchlist wire state: quoted items for the ACTIVE list + tab metadata."""
    state = store.state()
    return {
        "items": await _quote_items(state["entries"], cache),
        "lists": state["lists"],
        "active": state["active"],
    }


async def _respond_state(
    request_id: str,
    send_json: SendJson,
    store: WatchlistStore,
    cache: PriceCache,
) -> None:
    await send_json(
        make_response_frame(
            ResponseFrame(id=request_id, ok=True, payload=await _state_payload(store, cache))
        )
    )


async def handle_market_watchlist_get(request_id: str, params: dict[str, Any] | None, send_json: SendJson, orchestrator) -> None:
    del params
    await _respond_state(request_id, send_json, watchlist_store(orchestrator), price_cache(orchestrator))


async def handle_market_watchlist_add(request_id: str, params: dict[str, Any] | None, send_json: SendJson, orchestrator) -> None:
    raw = params or {}
    symbol = str(raw.get("symbol") or "").strip().upper()
    name = str(raw.get("name") or "").strip()
    list_name = str(raw.get("list") or "").strip() or None
    if not symbol:
        raise ValueError("symbol is required")
    cache = price_cache(orchestrator)
    probe = await asyncio.to_thread(quote_row, cache, symbol)
    if probe is None:
        raise ValueError(f"'{symbol}' did not resolve to a tradable ticker")
    store = watchlist_store(orchestrator)
    store.add(symbol, name, list_name)
    await _respond_state(request_id, send_json, store, cache)


async def handle_market_watchlist_remove(request_id: str, params: dict[str, Any] | None, send_json: SendJson, orchestrator) -> None:
    raw = params or {}
    symbol = str(raw.get("symbol") or "").strip().upper()
    list_name = str(raw.get("list") or "").strip() or None
    if not symbol:
        raise ValueError("symbol is required")
    store = watchlist_store(orchestrator)
    store.remove(symbol, list_name)
    await _respond_state(request_id, send_json, store, price_cache(orchestrator))


async def handle_market_watchlist_list_create(request_id: str, params: dict[str, Any] | None, send_json: SendJson, orchestrator) -> None:
    raw = params or {}
    store = watchlist_store(orchestrator)
    store.create_list(str(raw.get("name") or ""))
    await _respond_state(request_id, send_json, store, price_cache(orchestrator))


async def handle_market_watchlist_list_delete(request_id: str, params: dict[str, Any] | None, send_json: SendJson, orchestrator) -> None:
    raw = params or {}
    store = watchlist_store(orchestrator)
    store.delete_list(str(raw.get("name") or ""))
    await _respond_state(request_id, send_json, store, price_cache(orchestrator))


async def handle_market_watchlist_list_select(request_id: str, params: dict[str, Any] | None, send_json: SendJson, orchestrator) -> None:
    raw = params or {}
    store = watchlist_store(orchestrator)
    store.select_list(str(raw.get("name") or ""))
    await _respond_state(request_id, send_json, store, price_cache(orchestrator))


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
