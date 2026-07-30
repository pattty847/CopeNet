from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from copenet.core.tools.contracts import ToolExecutionRequest
from copenet.core.tools.handlers import market_evidence


@dataclass
class _EvidencePayload:
    wire: dict[str, Any]

    def to_wire(self) -> dict[str, Any]:
        return dict(self.wire)


@pytest.mark.asyncio
async def test_market_evidence_returns_compact_classified_packet(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, Any] = {}

    async def fake_evidence(symbol: str, *, refresh: bool, days_back: int) -> _EvidencePayload:
        calls.update(symbol=symbol, refresh=refresh, days_back=days_back)
        return _EvidencePayload(
            {
                "symbol": symbol,
                "asOf": "2026-07-17T00:00:00Z",
                "refreshed": refresh,
                "events": [{"kind": "insider"}],
                "insiderNet": {
                    "d90": {"days": 90, "buys": 1, "sells": 3, "netValue": -1200000, "tone": "down"}
                },
                "evidence": [
                    {
                        "type": "Insider",
                        "headline": f"Officer {index} sold shares",
                        "source": "SEC Form 4",
                        "url": f"https://sec.example/{index}",
                    }
                    for index in range(4)
                ],
            }
        )

    async def fake_fundamentals(symbol: str, *, refresh: bool = False) -> dict[str, Any]:
        assert refresh is True
        return {"entityName": "Apple Inc.", "revenueQuarterly": [{"date": "2026-06-30", "value": 1}]}

    monkeypatch.setattr(market_evidence, "fetch_ticker_evidence", fake_evidence)
    monkeypatch.setattr(market_evidence, "fetch_fundamentals", fake_fundamentals)

    result = await market_evidence.get_market_evidence(
        ToolExecutionRequest(
            tool_id="market.evidence",
            arguments={"symbol": " aapl ", "daysBack": 60, "limit": 2, "refresh": True},
        ),
        object(),  # type: ignore[arg-type] - the read-only handler does not consume runtime context
    )

    assert result.ok is True
    assert calls == {"symbol": "AAPL", "refresh": True, "days_back": 60}
    assert result.output["evidenceCount"] == 4
    assert result.output["evidenceReturned"] == 2
    assert "events" not in result.output
    assert result.output["fundamentals"]["entityName"] == "Apple Inc."
    assert "1 buys / 3 sells" in result.summary


@pytest.mark.asyncio
async def test_market_evidence_can_skip_fundamentals(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_evidence(symbol: str, *, refresh: bool, days_back: int) -> _EvidencePayload:
        return _EvidencePayload({"symbol": symbol, "evidence": [], "events": [], "insiderNet": None})

    async def forbidden_fundamentals(symbol: str) -> dict[str, Any]:
        raise AssertionError(f"fundamentals should not be fetched for {symbol}")

    monkeypatch.setattr(market_evidence, "fetch_ticker_evidence", fake_evidence)
    monkeypatch.setattr(market_evidence, "fetch_fundamentals", forbidden_fundamentals)

    result = await market_evidence.get_market_evidence(
        ToolExecutionRequest(
            tool_id="market.evidence",
            arguments={"symbol": "SPY", "includeFundamentals": False},
        ),
        object(),  # type: ignore[arg-type]
    )

    assert result.output["fundamentals"] is None
    assert result.output["daysBack"] == 90
