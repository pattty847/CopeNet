from __future__ import annotations

from pathlib import Path

from copenet.core.market.models import (
    Briefing,
    DashboardPayload,
    MacroItem,
    MarketBar,
    MarketPanel,
)
from copenet.core.market.store import MarketStore


def test_market_store_persists_bars_signals_and_latest_dashboard(tmp_path: Path) -> None:
    store = MarketStore(tmp_path / "market")

    store.save_bars(
        "GOOG",
        "weekly",
        [
            MarketBar(t=1_783_036_800, o=100.0, h=110.0, l=98.0, c=108.0, v=12_000_000),
            MarketBar(t=1_783_641_600, o=108.0, h=112.0, l=105.0, c=110.0, v=13_000_000),
        ],
    )
    store.save_signals("GOOG", {"trendDirection": "up", "drawdown": "-2.0%"})

    dashboard = DashboardPayload.empty(as_of="as of Fri 4:00pm ET close")
    dashboard.macro = MarketPanel(
        status="live",
        data=[
            MacroItem(
                label="VIX",
                value="15.2",
                change="-1.1%",
                tone="down",
                spark=[14.8, 15.0, 15.2],
            )
        ],
        as_of="2026-06-26T20:00:00Z",
    )
    dashboard.briefing = MarketPanel(
        status="live",
        data=Briefing(
            headline="Risk-on, but verify the breadth.",
            summary="The weekly tape is constructive while volatility remains contained.",
            changed=[{"text": "chop -> risk-on", "tone": "up"}],
            attention=[],
            vix=15.2,
            breadth_pct=61.0,
        ),
    )
    store.save_dashboard(dashboard)

    reloaded = MarketStore(tmp_path / "market")

    assert [bar.c for bar in reloaded.load_bars("GOOG", "weekly")] == [108.0, 110.0]
    assert reloaded.load_signals("GOOG")["trendDirection"] == "up"
    payload = reloaded.load_dashboard().to_wire()
    assert payload["asOf"] == "as of Fri 4:00pm ET close"
    assert payload["macro"]["status"] == "live"
    assert payload["macro"]["data"][0]["label"] == "VIX"
    assert "breadthPct" in payload["briefing"]["data"]
