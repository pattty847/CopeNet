"""Regression coverage for the market refresh cache-preservation + stale-regime guard.

Confirmed audit finding (2026-07-24, C-A-015): a failed/empty fetch used to
unconditionally overwrite MarketStore's cached bars, and a total-failure cycle
(0.0 breadth) was published as a confident `status="live", current="risk-off"`
regime rather than being surfaced as a fetch failure. See docs/audit/.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from copenet.core.market import runtime as runtime_module
from copenet.core.market.models import MarketBar
from copenet.core.market.runtime import MarketRuntime
from copenet.core.market.store import MarketStore


def _seed_good_bars(store: MarketStore, symbol: str, timeframe: str) -> None:
    store.save_bars(
        symbol,
        timeframe,
        [MarketBar(t=1, o=100.0, h=101.0, l=99.0, c=100.5, v=1000)],
    )


def test_refresh_preserves_cached_bars_when_fetch_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = MarketStore(tmp_path / "market")
    _seed_good_bars(store, "GOOG", "weekly")
    _seed_good_bars(store, "GOOG", "daily")

    def _always_fails(*args: Any, **kwargs: Any) -> pd.DataFrame:
        raise RuntimeError("simulated transient fetch failure")

    monkeypatch.setattr(runtime_module, "fetch_ohlcv", _always_fails)

    runtime = MarketRuntime(store=store)
    runtime.refresh(scope="all")

    # A transient failure must never wipe the previously-good cache — downstream
    # readers (ticker(), interpret(), backtester, ledger) rely on it as fallback.
    assert store.load_bars("GOOG", "weekly") != []
    assert store.load_bars("GOOG", "daily") != []


def test_refresh_marks_regime_stale_not_live_riskoff_on_total_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = MarketStore(tmp_path / "market")

    def _always_fails(*args: Any, **kwargs: Any) -> pd.DataFrame:
        raise RuntimeError("simulated total outage")

    monkeypatch.setattr(runtime_module, "fetch_ohlcv", _always_fails)
    monkeypatch.setattr(runtime_module, "fetch_fund_profile", lambda symbol: None)
    monkeypatch.setattr(runtime_module, "fetch_key_stats", lambda symbol: None)

    async def _no_evidence(symbols: list[str]) -> list[Any]:
        return []

    monkeypatch.setattr(runtime_module, "fetch_evidence", _no_evidence)

    runtime = MarketRuntime(store=store)
    dashboard = runtime.refresh(scope="all")

    # 0.0 breadth from a total fetch failure is not a genuine risk-off reading —
    # it must be surfaced as stale, never published as a confident "live" regime.
    assert dashboard.regime.status == "stale"
    assert dashboard.regime.note is not None
    assert dashboard.briefing.status == "stale"
