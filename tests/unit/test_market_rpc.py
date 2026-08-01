from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from copenet.core.market import runtime as runtime_module
from copenet.core.market.models import DashboardPayload
from copenet.core.market.runtime import MarketRuntime
from copenet.core.market.store import MarketStore
from copenet.host.rpc_market import (
    handle_market_dashboard_get,
    handle_market_refresh,
    handle_market_ticker_get,
    handle_market_universe_get,
)


class FakeOrchestrator:
    def __init__(self, root: Path) -> None:
        self.market_store = MarketStore(root / "market")
        self._background_tasks: set[asyncio.Task] = set()


@pytest.fixture(autouse=True)
def offline_market(monkeypatch: pytest.MonkeyPatch) -> None:
    """These tests assert RPC wire shapes only — never let them reach Yahoo or SEC EDGAR.

    ticker() fetches live OHLCV/fund-profile/key-stats with store fallbacks, and
    refresh() sweeps the whole universe (yfinance + SEC evidence into the shared
    data/edgar cache). Unpatched, this suite made real network calls on every run."""

    def _no_network(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("network disabled in unit tests")

    monkeypatch.setattr(runtime_module, "fetch_ohlcv", _no_network)
    monkeypatch.setattr(runtime_module, "fetch_fund_profile", lambda symbol: None)
    monkeypatch.setattr(runtime_module, "fetch_key_stats", lambda symbol: None)


async def test_market_dashboard_get_returns_contract_payload(tmp_path: Path) -> None:
    orchestrator = FakeOrchestrator(tmp_path)
    orchestrator.market_store.save_dashboard(DashboardPayload.empty(as_of="as of cached close"))
    frames: list[dict[str, Any]] = []

    async def send_json(frame: dict[str, Any]) -> None:
        frames.append(frame)

    await handle_market_dashboard_get("req-1", {}, send_json, orchestrator)

    frame = frames[0]
    assert frame["ok"] is True
    assert frame["payload"]["asOf"] == "as of cached close"
    assert frame["payload"]["briefing"]["status"] in {"preview", "live", "stale", "error"}


async def test_market_universe_and_ticker_get_return_camel_case_shapes(tmp_path: Path) -> None:
    orchestrator = FakeOrchestrator(tmp_path)
    frames: list[dict[str, Any]] = []

    async def send_json(frame: dict[str, Any]) -> None:
        frames.append(frame)

    await handle_market_universe_get("universe", {}, send_json, orchestrator)
    await handle_market_ticker_get("ticker", {"symbol": "GOOG"}, send_json, orchestrator)

    universe = frames[0]["payload"]
    ticker = frames[1]["payload"]
    assert {"symbol": "VOO", "name": "Vanguard S&P 500 ETF", "role": "index"} in universe
    assert ticker["symbol"] == "GOOG"
    assert set(ticker["series"].keys()) == {"daily", "weekly", "monthly"}
    assert "pnlPct" not in ticker
    # Insight Engine: ticker carries the soft_bottoming flag + decomposed components
    assert "insight" in ticker
    assert "softBottoming" in ticker["insight"]


async def test_market_refresh_returns_run_identifier(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    orchestrator = FakeOrchestrator(tmp_path)
    refresh_scopes: list[str] = []

    def _fake_refresh(self: MarketRuntime, *, scope: str = "all") -> DashboardPayload:
        refresh_scopes.append(scope)
        return DashboardPayload.empty(as_of="test")

    monkeypatch.setattr(MarketRuntime, "refresh", _fake_refresh)
    frames: list[dict[str, Any]] = []

    async def send_json(frame: dict[str, Any]) -> None:
        frames.append(frame)

    await handle_market_refresh("refresh", {"scope": "macro"}, send_json, orchestrator)
    # The handler fire-and-forgets the refresh; drain it so nothing outlives the test.
    await asyncio.gather(*orchestrator._background_tasks)

    payload = frames[0]["payload"]
    assert frames[0]["ok"] is True
    assert payload["runId"].startswith("market-refresh-")
    assert payload["startedAt"].endswith("Z")
    assert refresh_scopes == ["macro"]
