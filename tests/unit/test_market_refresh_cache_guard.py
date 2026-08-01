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
from copenet.core.market import price_cache as price_cache_module
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

    monkeypatch.setattr(price_cache_module, "fetch_daily_price_history", _always_fails)

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

    monkeypatch.setattr(price_cache_module, "fetch_daily_price_history", _always_fails)
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


def test_refresh_makes_exactly_one_price_request_per_symbol(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The morning sweep used to fire two downloads per symbol, every single day.

    One cached daily history now serves both the weekly and daily signal frames, so a
    universe sweep costs one request per symbol: a full-history pull the first time and a
    small delta every morning after. This pins that, because quietly regressing to
    per-timeframe fetches is invisible in output and only shows up as rate limiting.
    """
    calls: list[tuple[str, str]] = []

    def _record(symbol: str, *, period: str = "max"):
        calls.append((symbol, period))
        return (
            pd.DataFrame(
                {
                    "date": pd.to_datetime(["2026-03-02", "2026-03-03"]),
                    "open": [10.0, 11.0],
                    "high": [12.0, 12.0],
                    "low": [9.0, 10.0],
                    "close": [11.0, 11.5],
                    "volume": [100, 120],
                }
            ),
            [],
            [],
        )

    monkeypatch.setattr(price_cache_module, "fetch_daily_price_history", _record)
    monkeypatch.setattr(runtime_module, "fetch_fund_profile", lambda symbol: None)
    monkeypatch.setattr(runtime_module, "fetch_key_stats", lambda symbol: None)

    async def _no_evidence(symbols: list[str]) -> list[Any]:
        return []

    monkeypatch.setattr(runtime_module, "fetch_evidence", _no_evidence)
    monkeypatch.setenv("COPNET_MARKET_FETCH_PACE", "0")
    runtime = MarketRuntime(store=MarketStore(tmp_path / "market"))

    runtime.refresh(scope="macro")
    first_sweep = list(calls)
    calls.clear()
    runtime.refresh(scope="macro")

    symbols = [symbol for symbol, _ in first_sweep]
    assert len(symbols) == len(set(symbols)), "one request per symbol, not one per timeframe"
    assert {period for _, period in first_sweep} == {"max"}
    # Every sweep after the first is a delta, never a re-pull of full history.
    assert calls == [(symbol, "6mo") for symbol in symbols]
