from __future__ import annotations

from typing import Any

import pytest

from copenet.core.tools.contracts import ToolExecutionRequest
from copenet.core.tools.handlers import market_financials
from copenet.host import rpc_market


def _payload() -> dict[str, Any]:
    return {
        "symbol": "NVDA",
        "metric": "revenue",
        "frequency": "quarterly",
        "basis": "canonical",
        "alignment": "availability",
        "normalizationVersion": 1,
        "rawFactCount": 10,
        "warnings": ["derived_q4"],
        "observations": [
            {
                "periodStart": "2024-10-28",
                "periodEnd": "2025-01-26",
                "availableAt": "2025-02-26",
                "alignedAt": "2025-02-26",
                "value": 39_331_000_000,
                "unit": "USD",
                "frequency": "quarterly",
                "reported": False,
                "derived": True,
                "confidence": 0.9,
                "qualityFlags": ["derived_q4"],
                "sources": [],
            }
        ],
    }


@pytest.mark.asyncio
async def test_market_financials_tool_uses_canonical_service(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, Any] = {}

    async def fake_get_financial_series(**kwargs):
        calls.update(kwargs)
        return _payload()

    monkeypatch.setattr(market_financials, "get_financial_series", fake_get_financial_series)
    result = await market_financials.get_market_financials(
        ToolExecutionRequest(
            tool_id="market.financials",
            arguments={
                "symbol": " nvda ",
                "frequency": "quarterly",
                "asOf": "2025-03-01",
            },
        ),
        object(),  # type: ignore[arg-type]
    )

    assert result.ok is True
    assert calls["symbol"] == "NVDA"
    assert calls["alignment"] == "availability"
    assert calls["as_of"] == "2025-03-01"
    assert result.output["observations"][0]["availableAt"] == "2025-02-26"


@pytest.mark.asyncio
async def test_financial_series_rpc_returns_same_canonical_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, Any] = {}
    frames: list[dict[str, Any]] = []

    async def fake_get_financial_series(**kwargs):
        calls.update(kwargs)
        return _payload()

    async def send_json(frame: dict[str, Any]) -> None:
        frames.append(frame)

    monkeypatch.setattr(rpc_market, "get_financial_series", fake_get_financial_series)
    await rpc_market.handle_market_financial_series_get(
        "req-1",
        {
            "symbol": "NVDA",
            "metric": "revenue",
            "frequency": "quarterly",
            "basis": "canonical",
            "alignment": "availability",
        },
        send_json,
        object(),
    )

    assert calls["symbol"] == "NVDA"
    assert calls["include_provenance"] is True
    assert frames[0]["ok"] is True
    assert frames[0]["payload"]["series"]["observations"][0]["derived"] is True
