"""market.watchlist.* + market.symbols.search — the user-curated ticker list.

fetch_quote_row / search_symbols are the real I/O boundaries and are monkeypatched, so these
tests never touch the network.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from copenet.core.market.models import MacroItem
from copenet.core.market.store import MarketStore
from copenet.host import rpc_market_watchlist as handlers


class FakeOrchestrator:
    def __init__(self, root: Path) -> None:
        self.market_store = MarketStore(root / "market")


async def _send(handler, params: dict[str, Any] | None, orchestrator) -> dict[str, Any]:
    frames: list[dict[str, Any]] = []

    async def send_json(frame: dict[str, Any]) -> None:
        frames.append(frame)

    await handler("req-1", params, send_json, orchestrator)
    return frames[0]


def _fake_quote(symbol: str) -> MacroItem | None:
    if symbol == "ZZZZ":
        return None
    return MacroItem(label=symbol, value="$123.45", change="+1.00%", tone="up", spark=[120.0, 123.45])


async def test_watchlist_add_get_remove_round_trip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(handlers, "fetch_quote_row", _fake_quote)
    orchestrator = FakeOrchestrator(tmp_path)

    added = await _send(handlers.handle_market_watchlist_add, {"symbol": "msft", "name": "Microsoft"}, orchestrator)
    assert added["ok"] is True
    assert added["payload"]["items"] == [
        {"symbol": "MSFT", "name": "Microsoft", "value": "$123.45", "change": "+1.00%", "tone": "up", "spark": [120.0, 123.45]}
    ]

    fetched = await _send(handlers.handle_market_watchlist_get, {}, orchestrator)
    assert fetched["payload"]["items"][0]["symbol"] == "MSFT"

    removed = await _send(handlers.handle_market_watchlist_remove, {"symbol": "MSFT"}, orchestrator)
    assert removed["payload"]["items"] == []


async def test_watchlist_add_rejects_unresolvable_symbol(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(handlers, "fetch_quote_row", _fake_quote)
    orchestrator = FakeOrchestrator(tmp_path)

    with pytest.raises(ValueError, match="did not resolve"):
        await _send(handlers.handle_market_watchlist_add, {"symbol": "ZZZZ"}, orchestrator)

    empty = await _send(handlers.handle_market_watchlist_get, {}, orchestrator)
    assert empty["payload"]["items"] == []


async def test_watchlist_add_is_idempotent_for_duplicate_symbol(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(handlers, "fetch_quote_row", _fake_quote)
    orchestrator = FakeOrchestrator(tmp_path)

    await _send(handlers.handle_market_watchlist_add, {"symbol": "MSFT"}, orchestrator)
    twice = await _send(handlers.handle_market_watchlist_add, {"symbol": "MSFT"}, orchestrator)
    assert len(twice["payload"]["items"]) == 1


async def test_watchlist_falls_back_to_universe_name_when_none_stored(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(handlers, "fetch_quote_row", _fake_quote)
    orchestrator = FakeOrchestrator(tmp_path)

    result = await _send(handlers.handle_market_watchlist_add, {"symbol": "GOOG"}, orchestrator)
    assert result["payload"]["items"][0]["name"] == "Alphabet Class C"


async def test_watchlist_store_is_scoped_to_orchestrators_market_store_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Regression: without deriving the watchlist path from orchestrator.market_store.root_dir,
    # a FakeOrchestrator with no `_market_watchlist_store` set would silently fall back to the
    # real ~/.copenet market dir instead of tmp_path.
    monkeypatch.setattr(handlers, "fetch_quote_row", _fake_quote)
    orchestrator = FakeOrchestrator(tmp_path)

    await _send(handlers.handle_market_watchlist_add, {"symbol": "MSFT"}, orchestrator)

    assert (tmp_path / "market" / "watchlist.json").exists()


async def test_symbols_search_wraps_results(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_search(query: str, *, limit: int) -> list[dict[str, str]]:
        captured["query"] = query
        captured["limit"] = limit
        return [{"symbol": "TSLA", "name": "Tesla, Inc.", "exchange": "NASDAQ"}]

    monkeypatch.setattr(handlers, "search_symbols", fake_search)
    orchestrator = FakeOrchestrator(tmp_path)

    result = await _send(handlers.handle_market_symbols_search, {"query": "tesla", "limit": 3}, orchestrator)
    assert result["payload"]["results"] == [{"symbol": "TSLA", "name": "Tesla, Inc.", "exchange": "NASDAQ"}]
    assert captured == {"query": "tesla", "limit": 3}


async def test_symbols_search_requires_no_query_to_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(handlers, "search_symbols", lambda query, *, limit: [])
    orchestrator = FakeOrchestrator(tmp_path)

    result = await _send(handlers.handle_market_symbols_search, {"query": ""}, orchestrator)
    assert result["payload"]["results"] == []
