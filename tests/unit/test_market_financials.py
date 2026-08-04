from __future__ import annotations

from typing import Any
from contextlib import asynccontextmanager

import pandas as pd
import pytest

from copenet.core.market import edgar
from copenet.core.market import financials as market_financials_service
from copenet.core.market import runtime as market_runtime
from copenet.core.market.price_cache import PriceCache
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
        "metric": "trailing_pe",
        "as_of": "2026-03-01",
        "refresh": True,
        "include_provenance": False,
    }


@pytest.mark.asyncio
async def test_every_valuation_metric_dispatches_with_its_own_id(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []

    async def fake_get_valuation_series(**kwargs):
        seen.append(kwargs["metric"])
        return {"symbol": "NVDA", "metric": kwargs["metric"], "observations": []}

    monkeypatch.setattr(
        market_financials_service,
        "get_valuation_series",
        fake_get_valuation_series,
    )

    for metric in sorted(market_financials_service.VALUATION_METRICS):
        payload = await market_financials_service.get_financial_series(
            symbol="NVDA",
            metric=metric,
        )
        assert payload is not None and payload["metric"] == metric

    assert seen == sorted(market_financials_service.VALUATION_METRICS)


def test_valuation_eligibility_covers_generic_multiple_provenance() -> None:
    cutoff = pd.Timestamp("2026-03-01", tz="UTC")
    eligible = market_financials_service._valuation_observation_is_eligible
    base = {"timestamp": "2026-02-01"}

    assert eligible({**base, "denominatorAvailableAt": "2026-01-15"}, cutoff)
    # SEC inputs filed after the price bar are lookahead, whatever the multiple.
    assert not eligible({**base, "denominatorAvailableAt": "2026-02-15"}, cutoff)
    assert not eligible({**base, "sharesAvailableAt": "2026-02-15"}, cutoff)
    assert not eligible({**base, "epsAvailableAt": "2026-02-15"}, cutoff)


def test_metric_listing_is_unique_complete_and_frequency_honest() -> None:
    metrics = market_financials_service.supported_financial_metrics()
    by_id = {entry["id"]: entry for entry in metrics}

    assert len(by_id) == len(metrics)
    assert set(market_financials_service.VALUATION_METRICS) <= set(by_id)
    assert all(entry.get("frequencies") for entry in metrics)
    for metric in market_financials_service.VALUATION_METRICS:
        assert by_id[metric]["factType"] == "valuation"
        assert by_id[metric]["frequencies"] == ["ttm"]
    assert by_id["stockholders_equity"]["frequencies"] == ["quarterly", "annual"]
    assert by_id["revenue_per_share"]["frequencies"] == ["quarterly", "annual"]
    assert by_id["roic"]["frequencies"] == ["ttm"]


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


def test_valuation_prices_are_split_only_and_never_dividend_adjusted(tmp_path) -> None:
    """A P/E numerator must be the price that actually traded.

    Dividend-adjusted prices back-shift history downward, so the same EPS over a lower
    price reads as a lower multiple — historical P/E understated by an amount that grows
    with lookback and dividend yield. This pins the split-only basis so the fix cannot be
    silently undone by anyone reaching for the more convenient adjusted series.
    """
    def fake_fetch(_symbol: str, *, period: str = "max"):
        days = ["2026-01-05", "2026-01-06", "2026-01-12"]
        return (
            pd.DataFrame(
                {
                    "date": pd.to_datetime(days),
                    "open": [25.0] * 3,
                    "high": [25.0] * 3,
                    "low": [25.0] * 3,
                    "close": [25.0] * 3,
                    "volume": [10] * 3,
                }
            ),
            [("2025-06-01", 2.0)],
            [("2026-01-06", 5.0)],  # a dividend big enough to be obvious if applied
        )

    cache = PriceCache(tmp_path, fetch=fake_fetch)

    prices, splits = market_financials_service._valuation_price_inputs(
        "NVDA",
        prices_cache=cache,
    )

    # Weekly closes, Monday-anchored, untouched by the dividend.
    assert prices == [
        {"time": "2026-01-05", "close": 25.0},
        {"time": "2026-01-12", "close": 25.0},
    ]
    assert splits == [("2025-06-01", 2.0)]


def test_valuation_prices_come_from_the_cache_without_a_second_download(tmp_path) -> None:
    calls: list[str] = []

    def fake_fetch(_symbol: str, *, period: str = "max"):
        calls.append(period)
        return (
            pd.DataFrame(
                {
                    "date": pd.to_datetime(["2026-01-05"]),
                    "open": [25.0],
                    "high": [25.0],
                    "low": [25.0],
                    "close": [25.0],
                    "volume": [10],
                }
            ),
            [],
            [],
        )

    cache = PriceCache(tmp_path, fetch=fake_fetch)
    market_financials_service._valuation_price_inputs("NVDA", prices_cache=cache)
    market_financials_service._valuation_price_inputs("NVDA", prices_cache=cache)

    # Turning the P/E overlay on used to cost a fresh 10y weekly download every time.
    assert calls == ["max"]


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
    result = market_runtime._trailing_eps_and_pe(
        {
            "epsTtm": 2.0,
            "epsTtmAvailableAt": "2026-02-01",
        },
        20.0,
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
        20.0,
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
        20.0,
        "TEST",
    )

    assert result["epsTtmReported"] == 2.0
    assert result["epsTtm"] is None
    assert result["epsTtmSplitFactor"] is None
    assert result["peTtm"] is None


def test_valuation_series_trims_the_run_before_any_earnings_existed() -> None:
    """Price history reaches back decades further than XBRL does."""
    payload = {
        "observations": [
            {"timestamp": "1975-01-06", "value": None, "epsAvailableAt": None},
            {"timestamp": "2010-01-04", "value": None, "epsAvailableAt": None},
            {"timestamp": "2010-02-01", "value": 12.0, "epsAvailableAt": "2010-01-28"},
            # A gap *inside* the covered range is information — stale or negative
            # earnings — and must survive.
            {"timestamp": "2010-09-06", "value": None, "epsAvailableAt": None},
            {"timestamp": "2010-11-01", "value": 14.0, "epsAvailableAt": "2010-10-28"},
        ]
    }

    trimmed = market_financials_service._trim_leading_unpriced(payload)

    assert [row["timestamp"] for row in trimmed["observations"]] == [
        "2010-02-01",
        "2010-09-06",
        "2010-11-01",
    ]


def test_valuation_series_with_no_earnings_at_all_is_left_alone() -> None:
    payload = {"observations": [{"timestamp": "1975-01-06", "value": None, "epsAvailableAt": None}]}

    assert market_financials_service._trim_leading_unpriced(payload) == payload
