from __future__ import annotations

from typing import Any
from contextlib import asynccontextmanager

import pandas as pd
import pytest

from copenet.core.market import edgar
from copenet.core.market import financials as market_financials_service
from copenet.core.market import runtime as market_runtime
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


@pytest.mark.asyncio
async def test_trailing_pe_metric_dispatches_to_valuation_service(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, Any] = {}

    async def fake_get_valuation_series(**kwargs):
        calls.update(kwargs)
        return {"symbol": "NVDA", "metric": "trailing_pe", "observations": []}

    monkeypatch.setattr(
        market_financials_service,
        "get_valuation_series",
        fake_get_valuation_series,
    )

    payload = await market_financials_service.get_financial_series(
        symbol=" nvda ",
        metric="trailing_pe",
        as_of="2026-03-01",
        refresh=True,
        include_provenance=False,
    )

    assert payload is not None
    assert payload["metric"] == "trailing_pe"
    assert calls == {
        "symbol": "NVDA",
        "as_of": "2026-03-01",
        "refresh": True,
        "include_provenance": False,
    }


@pytest.mark.asyncio
async def test_financial_series_as_of_uses_available_at_and_preserves_provenance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_payload = {
        "symbol": "TEST",
        "metric": "revenue",
        "observations": [
            {
                "periodEnd": "2024-12-31",
                "availableAt": "2025-02-15",
                "value": 100,
                "sources": [{"accessionNumber": "old-original", "source": "sec"}],
            },
            {
                "periodEnd": "2025-03-31",
                "availableAt": "2025-05-15",
                "value": 120,
                "sources": [{"accessionNumber": "new-not-yet-filed", "source": "sec"}],
            },
            {
                "periodEnd": "2024-12-31",
                "availableAt": "2025-06-01",
                "value": 105,
                "sources": [{"accessionNumber": "later-restatement", "source": "sec"}],
            },
        ],
    }

    class FakeFinancials:
        async def series(self, _symbol: str, **_kwargs):
            return source_payload

    class FakeClient:
        financials = FakeFinancials()

    @asynccontextmanager
    async def fake_managed(*_args, **_kwargs):
        yield FakeClient()

    monkeypatch.setattr(market_financials_service, "managed_sec_fetcher", fake_managed)

    at_t = await market_financials_service.get_financial_series(
        symbol="TEST",
        metric="revenue",
        as_of="2025-05-01",
    )
    after_restatement = await market_financials_service.get_financial_series(
        symbol="TEST",
        metric="revenue",
        as_of="2025-07-01",
    )

    assert at_t is not None
    assert at_t["observations"] == [source_payload["observations"][0]]
    assert at_t["observations"][0]["sources"] == [
        {"accessionNumber": "old-original", "source": "sec"}
    ]
    assert after_restatement is not None
    assert len(after_restatement["observations"]) == 3
    assert len(at_t["observations"]) == 1
    assert len(source_payload["observations"]) == 3


def test_valuation_as_of_uses_price_time_without_dropping_empty_eps_rows() -> None:
    payload = {
        "metric": "trailing_pe",
        "priceBasis": "split_adjusted",
        "observations": [
            {
                "timestamp": "2026-02-01",
                "epsAvailableAt": None,
                "value": None,
            },
            {
                "timestamp": "2026-03-01",
                "epsAvailableAt": "2026-02-20",
                "value": 10,
            },
            {
                "timestamp": "2026-04-01",
                "epsAvailableAt": "2026-03-20",
                "value": 8,
            },
            {
                "timestamp": "2026-03-01",
                "epsAvailableAt": "2026-03-20",
                "value": 7,
            },
        ],
    }

    result = market_financials_service._point_in_time_valuation_payload(
        payload,
        as_of="2026-03-15",
    )

    assert result is not None
    assert result["priceBasis"] == "split_adjusted"
    assert [row["value"] for row in result["observations"]] == [None, 10]


def test_valuation_price_inputs_preserve_split_adjusted_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, Any] = {}

    def fake_fetch_ohlcv(symbol: str, **kwargs):
        calls.update({"symbol": symbol, **kwargs})
        return pd.DataFrame(
            {
                "date": pd.to_datetime(["2026-01-02"], utc=True),
                "close": [25.0],
            }
        )

    monkeypatch.setattr(market_financials_service, "fetch_ohlcv", fake_fetch_ohlcv)
    monkeypatch.setattr(
        market_financials_service,
        "fetch_split_history",
        lambda _symbol: ([("2025-06-01", 2.0)], True),
    )

    prices, splits = market_financials_service._valuation_price_inputs("NVDA")

    assert calls["auto_adjust"] is True
    assert calls["interval"] == "1wk"
    assert prices == [{"time": "2026-01-02", "close": 25.0}]
    assert splits == [("2025-06-01", 2.0)]


@pytest.mark.asyncio
async def test_fundamentals_use_canonical_diluted_eps(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        edgar,
        "fetch_split_history",
        lambda _symbol: ([("2025-06-01", 2.0)], True),
    )

    class FakeFinancials:
        async def series(self, _symbol: str, *, metric: str, frequency: str, **_kwargs):
            calls.append((metric, frequency))
            unit = "USD/shares" if metric == "diluted_eps" else "USD"
            return {
                "entityName": "Fixture Corp",
                "metric": metric,
                "frequency": frequency,
                "shareBasis": "split_adjusted" if frequency == "ttm" else None,
                "warnings": [],
                "observations": [
                    {
                        "periodEnd": "2025-12-31",
                        "availableAt": "2026-02-01",
                        "value": 4 if frequency == "ttm" else 1,
                        "unit": unit,
                        "fiscalPeriod": "FY" if frequency == "annual" else "Q4",
                        "fiscalYear": 2025,
                        "sources": [{"form": "10-K"}],
                    }
                ],
            }

    class FakeClient:
        financials = FakeFinancials()

    @asynccontextmanager
    async def fake_managed(*_args, **_kwargs):
        yield FakeClient()

    monkeypatch.setattr(edgar, "managed_sec_fetcher", fake_managed)

    payload = await edgar.fetch_fundamentals("TEST")

    assert payload is not None
    assert payload["epsQuarterly"][0]["value"] == 1
    assert payload["epsTtm"] == 4
    assert payload["epsTtmShareBasis"] == "split_adjusted"
    assert ("diluted_eps", "ttm") in calls


@pytest.mark.asyncio
async def test_diluted_eps_ttm_series_passes_verified_split_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, Any] = {}

    class FakeFinancials:
        async def series(self, _symbol: str, **kwargs):
            calls.update(kwargs)
            return {"metric": "diluted_eps", "frequency": "ttm", "observations": []}

    class FakeClient:
        financials = FakeFinancials()

    @asynccontextmanager
    async def fake_managed(*_args, **_kwargs):
        yield FakeClient()

    monkeypatch.setattr(market_financials_service, "managed_sec_fetcher", fake_managed)
    monkeypatch.setattr(
        market_financials_service,
        "fetch_split_history",
        lambda _symbol: ([("2022-07-15", 20.0)], True),
    )

    await market_financials_service.get_financial_series(
        symbol="GOOG",
        metric="diluted_eps",
        frequency="ttm",
    )

    assert calls["split_events"] == [("2022-07-15", 20.0)]


def test_latest_pe_uses_canonical_ttm_eps_on_the_current_split_basis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        market_runtime,
        "fetch_split_history",
        lambda _symbol: ([("2026-03-01", 2.0)], True),
    )
    weekly = pd.DataFrame({"close": [20.0]})

    result = market_runtime._trailing_eps_and_pe(
        {
            "epsTtm": 2.0,
            "epsTtmAvailableAt": "2026-02-01",
        },
        weekly,
        "TEST",
    )

    assert result == {
        "epsTtm": 1.0,
        "epsTtmReported": 2.0,
        "epsTtmSplitFactor": 2.0,
        "peTtm": 20.0,
    }


def test_latest_pe_does_not_double_adjust_canonical_split_basis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden_split_history(_symbol: str):
        raise AssertionError("split-adjusted EPS must not be adjusted twice")

    monkeypatch.setattr(market_runtime, "fetch_split_history", forbidden_split_history)

    result = market_runtime._trailing_eps_and_pe(
        {
            "epsTtm": 2.0,
            "epsTtmAvailableAt": "2026-02-01",
            "epsTtmShareBasis": "split_adjusted",
        },
        pd.DataFrame({"close": [20.0]}),
        "TEST",
    )

    assert result == {
        "epsTtm": 2.0,
        "epsTtmReported": 2.0,
        "epsTtmSplitFactor": 1.0,
        "peTtm": 10.0,
    }


def test_latest_pe_is_unavailable_when_split_history_cannot_be_verified(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        market_runtime,
        "fetch_split_history",
        lambda _symbol: ([], False),
    )

    result = market_runtime._trailing_eps_and_pe(
        {
            "epsTtm": 2.0,
            "epsTtmAvailableAt": "2026-02-01",
        },
        pd.DataFrame({"close": [20.0]}),
        "TEST",
    )

    assert result["epsTtmReported"] == 2.0
    assert result["epsTtm"] is None
    assert result["epsTtmSplitFactor"] is None
    assert result["peTtm"] is None
