from __future__ import annotations

from pathlib import Path
from typing import Any

from copenet.core.market.models import DashboardPayload
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


async def _capture(handler, *args) -> dict[str, Any]:
    frames: list[dict[str, Any]] = []

    async def send_json(frame: dict[str, Any]) -> None:
        frames.append(frame)

    await handler("req-1", *args, send_json, FakeOrchestrator(Path(args[-1]) if args and isinstance(args[-1], str) else Path.cwd()))
    return frames[0]


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
    assert {"symbol": "GOOG", "name": "Alphabet Class C", "role": "holding"} in universe
    assert ticker["symbol"] == "GOOG"
    assert set(ticker["series"].keys()) == {"daily", "weekly", "monthly"}
    assert "pnlPct" not in ticker
    # Insight Engine: ticker carries the soft_bottoming flag + decomposed components
    assert "insight" in ticker
    assert "softBottoming" in ticker["insight"]


async def test_market_refresh_returns_run_identifier(tmp_path: Path) -> None:
    orchestrator = FakeOrchestrator(tmp_path)
    frames: list[dict[str, Any]] = []

    async def send_json(frame: dict[str, Any]) -> None:
        frames.append(frame)

    await handle_market_refresh("refresh", {"scope": "macro"}, send_json, orchestrator)

    payload = frames[0]["payload"]
    assert frames[0]["ok"] is True
    assert payload["runId"].startswith("market-refresh-")
    assert payload["startedAt"].endswith("Z")
