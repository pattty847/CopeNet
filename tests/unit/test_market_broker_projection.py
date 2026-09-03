"""A broker sync updates account context, never launches a market-wide scan."""
import asyncio
from types import SimpleNamespace

import pytest

from copenet.core.market.runtime import resolve_market_runtime
from copenet.core.market.store import MarketStore
from copenet.host import rpc_market_webull


@pytest.mark.asyncio
async def test_broker_sync_updates_only_cached_portfolio_without_market_acquisition(tmp_path, monkeypatch):
    from copenet.core.market.webull import client, sync
    orchestrator = SimpleNamespace(market_store=MarketStore(tmp_path), _background_tasks=set())
    runtime = resolve_market_runtime(orchestrator)
    original = runtime.store.load_dashboard_wire()
    snapshot = {"synced_at": "2026-09-03T14:00:00Z", "total_equity": 100,
                "positions": [{"symbol": "TEST", "quantity": 1, "avg_cost": 90, "last_price": 100,
                               "market_value": 100, "unrealized_pl_pct": 11.11}]}
    monkeypatch.setattr(rpc_market_webull, "_config", lambda: object())
    monkeypatch.setattr(rpc_market_webull, "_account_id", lambda: "synthetic-account")
    monkeypatch.setattr(client, "trade_client", lambda _: object())
    monkeypatch.setattr(sync, "fetch_snapshot", lambda *args: SimpleNamespace(to_dict=lambda: snapshot))
    monkeypatch.setattr(runtime, "refresh", lambda **kwargs: pytest.fail("Broker sync launched a broad market refresh"))
    monkeypatch.setattr(runtime.prices, "refresh", lambda *args, **kwargs: pytest.fail("Broker sync requested Yahoo"))
    frames = []
    async def send(frame):
        frames.append(frame)
    await rpc_market_webull.handle_market_webull_sync("sync", {}, send, orchestrator)
    await asyncio.gather(*orchestrator._background_tasks)
    current = runtime.store.load_dashboard_wire()
    assert current["portfolio"]["status"] == "live"
    assert current["portfolio"]["asOf"] == snapshot["synced_at"]
    assert current["portfolio"]["data"]["positions"][0]["symbol"] == "TEST"
    assert {key: value for key, value in current.items() if key != "portfolio"} == {key: value for key, value in original.items() if key != "portfolio"}
    assert frames[0]["ok"]


def test_empty_broker_portfolio_clears_only_previous_holdings(tmp_path):
    orchestrator = SimpleNamespace(market_store=MarketStore(tmp_path))
    runtime = resolve_market_runtime(orchestrator)
    runtime.update_portfolio({"positions": [], "total_equity": 0, "synced_at": "2026-09-03T14:00:00Z"})
    portfolio = runtime.store.load_dashboard_wire()["portfolio"]
    assert portfolio["status"] == "live"
    assert portfolio["data"]["positions"] == []
