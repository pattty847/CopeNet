from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from copenet.core.market import edgar
from copenet.core.market.store import MarketStore
from copenet.host.rpc_market import handle_market_ticker_evidence_get


class FakeFetcher:
    calls: list[str] = []

    def __init__(self, user_agent: str) -> None:
        self.user_agent = user_agent

    async def get_insider_signal_payload(self, symbol: str, *, days_back: int = 180, filing_limit: int = 40):
        self.calls.append(f"cached-insider:{symbol}:{days_back}:{filing_limit}")
        return _insider_payload(symbol)

    async def refresh_insider_signal_payload(self, symbol: str, *, days_back: int = 180, filing_limit: int = 40):
        self.calls.append(f"refresh-insider:{symbol}:{days_back}:{filing_limit}")
        return _insider_payload(symbol)

    async def get_8k_events(self, symbol: str, *, days_back: int = 180, filing_limit: int = 50):
        self.calls.append(f"cached-8k:{symbol}:{days_back}:{filing_limit}")
        return _form8k_payload(symbol)

    async def refresh_8k_events(self, symbol: str, *, days_back: int = 180, filing_limit: int = 50):
        self.calls.append(f"refresh-8k:{symbol}:{days_back}:{filing_limit}")
        return _form8k_payload(symbol)


class FakeOrchestrator:
    def __init__(self, root: Path) -> None:
        self.market_store = MarketStore(root / "market")


def _insider_payload(symbol: str) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "as_of": "2026-07-08T12:00:00Z",
        "events": [
            {
                "owner_name": "Jane Director",
                "owner_role": "Director",
                "shares": 1200,
                "is_acquisition": True,
                "is_disposition": False,
                "transaction_date": "2026-07-07",
                "filing_date": "2026-07-08",
                "form_url": "https://sec.example/form4",
            }
        ],
    }


def _form8k_payload(symbol: str) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "as_of": "2026-07-08T12:00:01Z",
        "events": [
            {
                "filing_date": "2026-07-06",
                "url": "https://sec.example/8k",
                "items": [{"label": "Departure or Election of Directors / Officers"}],
            }
        ],
    }


async def _capture(params: dict[str, Any], root: Path) -> dict[str, Any]:
    frames: list[dict[str, Any]] = []

    async def send_json(frame: dict[str, Any]) -> None:
        frames.append(frame)

    await handle_market_ticker_evidence_get("req-1", params, send_json, FakeOrchestrator(root))
    return frames[0]


@pytest.mark.asyncio
async def test_fetch_ticker_evidence_uses_cached_copetech_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeFetcher.calls = []
    monkeypatch.setattr(edgar, "_sec_fetcher_class", lambda: FakeFetcher)

    payload = await edgar.fetch_ticker_evidence("AAPL")

    assert [item.headline for item in payload.evidence] == [
        "Jane Director (Director) bought 1,200 shares",
        "Departure or Election of Directors / Officers",
    ]
    assert [event.kind for event in payload.events] == ["insider", "8-K"]
    assert FakeFetcher.calls == ["cached-insider:AAPL:180:40", "cached-8k:AAPL:180:5"]


@pytest.mark.asyncio
async def test_fetch_ticker_evidence_refresh_uses_incremental_copetech_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeFetcher.calls = []
    monkeypatch.setattr(edgar, "_sec_fetcher_class", lambda: FakeFetcher)

    payload = await edgar.fetch_ticker_evidence("AAPL", refresh=True)

    assert payload.refreshed is True
    assert FakeFetcher.calls == ["refresh-insider:AAPL:180:40", "refresh-8k:AAPL:180:5"]


@pytest.mark.asyncio
async def test_ticker_evidence_rpc_returns_camel_case_payload(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    FakeFetcher.calls = []
    monkeypatch.setattr(edgar, "_sec_fetcher_class", lambda: FakeFetcher)

    frame = await _capture({"symbol": "aapl", "refresh": True}, tmp_path)

    assert frame["ok"] is True
    assert frame["payload"]["symbol"] == "AAPL"
    assert frame["payload"]["refreshed"] is True
    assert frame["payload"]["evidence"][0]["source"] == "SEC Form 4"
    assert frame["payload"]["events"][0]["kind"] == "insider"


@pytest.mark.asyncio
async def test_ticker_evidence_missing_copetech_returns_empty_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(edgar, "_sec_fetcher_class", lambda: None)

    payload = await edgar.fetch_ticker_evidence("AAPL")

    assert payload.symbol == "AAPL"
    assert payload.evidence == []
    assert payload.events == []
    assert payload.refreshed is False
