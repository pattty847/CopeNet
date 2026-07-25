from __future__ import annotations

from pathlib import Path

from copenet.core.market.store import MarketStore
from copenet.host.rpc_market_calendar import handle_market_calendar_get


class FakeOrchestrator:
    def __init__(self, root: Path) -> None:
        self.market_store = MarketStore(root / "market")


async def test_market_calendar_rpc_returns_configuration_state(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("TRADING_ECONOMICS_API_KEY", raising=False)
    frames = []

    async def send_json(frame):
        frames.append(frame)

    await handle_market_calendar_get("calendar", {"days": 7}, send_json, FakeOrchestrator(tmp_path))

    assert frames[0]["ok"] is True
    assert frames[0]["payload"]["configured"] is False
    assert frames[0]["payload"]["events"] == []
