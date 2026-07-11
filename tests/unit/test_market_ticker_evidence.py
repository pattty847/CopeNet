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

    async def get_planned_insider_sales(self, symbol: str, *, days_back: int = 90, filing_limit: int = 25, use_cache: bool = True):
        self.calls.append(f"144:{symbol}:{days_back}:{filing_limit}:{'cached' if use_cache else 'live'}")
        return _form144_payload(symbol)


class FakeOrchestrator:
    def __init__(self, root: Path) -> None:
        self.market_store = MarketStore(root / "market")


def _insider_payload(symbol: str) -> dict[str, Any]:
    from datetime import datetime, timedelta, timezone

    recent = (datetime.now(timezone.utc) - timedelta(days=3)).strftime("%Y-%m-%d")
    older = (datetime.now(timezone.utc) - timedelta(days=60)).strftime("%Y-%m-%d")
    return {
        "symbol": symbol,
        "as_of": "2026-07-08T12:00:00Z",
        "events": [
            {
                "owner_name": "Jane Director",
                "owner_role": "Director",
                "shares": 1200,
                "gross_value": 24_000.0,
                "is_acquisition": True,
                "is_disposition": False,
                "transaction_date": recent,
                "filing_date": recent,
                "form_url": "https://sec.example/form4",
            },
            {
                "owner_name": "Sam Officer",
                "owner_role": "Officer",
                "shares": 5000,
                "gross_value": 100_000.0,
                "is_acquisition": False,
                "is_disposition": True,
                "transaction_date": older,
                "filing_date": older,
                "form_url": "https://sec.example/form4b",
            },
        ],
        "clusters": [
            {
                "window_start": "2026-07-01",
                "window_end": "2026-07-05",
                "unique_insiders": 3,
                "event_count": 4,
                "total_value": 1_250_000.0,
                "filing_urls": ["https://sec.example/form4-cluster"],
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
                "items": [{"label": "Departure or Election of Directors / Officers", "category": "exec_change"}],
                "high_signal": True,
            }
        ],
    }


def _form144_payload(symbol: str) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "as_of": "2026-07-08T12:00:02Z",
        "records": [
            {
                "account_name": "John CFO",
                "planned_shares": 50_000,
                "aggregate_market_value": 900_000.0,
                "signature_date": "2026-07-03",
                "filing_date": "2026-07-04",
                "form_url": "https://sec.example/form144",
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
        "Cluster buy — 3 insiders ~$1.2M (2026-07-01 → 2026-07-05)",
        "Jane Director (Director) bought 1,200 shares",
        "Sam Officer (Officer) sold 5,000 shares",
        "John CFO filed to sell 50,000 shares (~$900K)",
        "Departure or Election of Directors / Officers",
    ]
    assert [item.flag for item in payload.evidence] == ["cluster", None, None, None, "high-signal"]
    assert [item.type for item in payload.evidence] == ["Insider", "Insider", "Insider", "Form 144", "8-K"]
    assert [event.kind for event in payload.events] == ["insider", "insider", "insider", "planned-sale", "8-K"]
    # Net insider windows: recent buy only in 30d; buy + older sell in 90d.
    assert payload.insider_net is not None
    assert payload.insider_net["d30"]["net_shares"] == 1200
    assert payload.insider_net["d30"]["tone"] == "up"
    assert payload.insider_net["d90"]["net_shares"] == -3800
    assert payload.insider_net["d90"]["net_value"] == -76000
    assert payload.insider_net["d90"]["tone"] == "down"
    assert FakeFetcher.calls == [
        "cached-insider:AAPL:180:40",
        "144:AAPL:180:25:cached",
        "cached-8k:AAPL:180:6",
    ]


def test_insider_net_tone_follows_dollars_when_shares_and_value_diverge() -> None:
    # Vesting-style acquisitions inflate net shares with little gross value while real
    # money exits via sells — tone must follow net dollars, not the share count.
    from datetime import datetime, timedelta, timezone

    recent = (datetime.now(timezone.utc) - timedelta(days=3)).strftime("%Y-%m-%d")
    events = [
        {
            "shares": 400_000,
            "gross_value": 0,
            "is_acquisition": True,
            "is_disposition": False,
            "signal_class": "option_exercise",
            "transaction_date": recent,
        },
        {
            "shares": 2_000,
            "gross_value": 50_000.0,
            "is_acquisition": True,
            "is_disposition": False,
            "signal_class": "open_market_buy",
            "transaction_date": recent,
        },
        {
            "shares": 70_000,
            "gross_value": 230_050_000.0,
            "is_acquisition": False,
            "is_disposition": True,
            "signal_class": "open_market_sell",
            "transaction_date": recent,
        },
    ]

    windows = edgar._insider_net_windows(events)

    assert windows is not None
    assert windows["d30"]["net_shares"] == 332_000
    assert windows["d30"]["net_value"] == -230_000_000
    assert windows["d30"]["tone"] == "down"
    assert windows["d30"]["buys"] == 2
    assert windows["d30"]["open_market_buys"] == 1


def test_gift_transfers_are_neutral_and_excluded_from_net_windows() -> None:
    # Jensen Huang's Code G trust transfers (59M shares, $0) must not read as conviction
    # buys: the headline says what happened, the tone is flat, and net windows skip them.
    from datetime import datetime, timedelta, timezone

    recent = (datetime.now(timezone.utc) - timedelta(days=3)).strftime("%Y-%m-%d")
    gift = {
        "owner_name": "HUANG JEN HSUN",
        "owner_role": "Director, Officer (President and CEO)",
        "shares": 58_962_602,
        "gross_value": 0,
        "price_per_share": 0.0,
        "is_acquisition": True,
        "is_disposition": False,
        "signal_class": "gift",
        "transaction_date": recent,
    }

    item = edgar._insider_evidence("NVDA", gift)
    assert "transferred (gift)" in item.headline
    assert "bought" not in item.headline
    assert item.tone == "flat"

    real_sell = {
        "shares": 1_000,
        "gross_value": 200_000.0,
        "is_acquisition": False,
        "is_disposition": True,
        "signal_class": "open_market_sell",
        "transaction_date": recent,
    }
    windows = edgar._insider_net_windows([gift, real_sell])
    assert windows is not None
    assert windows["d30"]["buys"] == 0  # the gift is not a buy
    assert windows["d30"]["net_shares"] == -1_000
    assert windows["d30"]["tone"] == "down"


def test_mechanical_transactions_get_honest_verbs() -> None:
    from datetime import datetime, timedelta, timezone

    recent = (datetime.now(timezone.utc) - timedelta(days=3)).strftime("%Y-%m-%d")
    base = {"shares": 500, "is_acquisition": False, "is_disposition": True, "transaction_date": recent}
    tax = edgar._insider_evidence("NVDA", {**base, "signal_class": "tax_sale"})
    assert "sold (tax withholding)" in tax.headline and tax.tone == "flat"
    exercise = edgar._insider_evidence("NVDA", {**base, "is_acquisition": True, "is_disposition": False, "signal_class": "option_exercise"})
    assert "exercised options into" in exercise.headline and exercise.tone == "flat"
    buy = edgar._insider_evidence("NVDA", {**base, "is_acquisition": True, "is_disposition": False, "signal_class": "open_market_buy"})
    assert "bought" in buy.headline and buy.tone == "up"


def test_insider_net_tone_falls_back_to_shares_without_values() -> None:
    from datetime import datetime, timedelta, timezone

    recent = (datetime.now(timezone.utc) - timedelta(days=3)).strftime("%Y-%m-%d")
    events = [
        {
            "shares": 1_000,
            "is_acquisition": True,
            "is_disposition": False,
            "transaction_date": recent,
        }
    ]

    windows = edgar._insider_net_windows(events)

    assert windows is not None
    assert windows["d30"]["net_value"] is None
    assert windows["d30"]["tone"] == "up"


@pytest.mark.asyncio
async def test_fetch_ticker_evidence_refresh_uses_incremental_copetech_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeFetcher.calls = []
    monkeypatch.setattr(edgar, "_sec_fetcher_class", lambda: FakeFetcher)

    payload = await edgar.fetch_ticker_evidence("AAPL", refresh=True)

    assert payload.refreshed is True
    assert FakeFetcher.calls == [
        "refresh-insider:AAPL:180:40",
        "144:AAPL:180:25:live",
        "refresh-8k:AAPL:180:6",
    ]


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
