from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from copenet.core.market.fred import FredClient, _snapshot_row
from copenet.core.market.fred_catalog import FredSeriesSpec


@pytest.mark.asyncio
async def test_fred_series_caches_by_full_request_and_exposes_freshness(tmp_path: Path, monkeypatch) -> None:
    client = FredClient(tmp_path, api_key="test-key")
    calls: list[tuple[str, dict]] = []

    async def fake_request(endpoint: str, params: dict) -> dict:
        calls.append((endpoint, params))
        if endpoint == "series":
            return {"seriess": [{"id": "M2SL", "title": "M2", "frequency": "Monthly", "units": "Billions", "last_updated": "2026-09-01"}]}
        return {"observations": [{"date": "2026-08-01", "value": "22000.0"}]}

    monkeypatch.setattr(client, "_request", fake_request)
    first = await client.series("M2SL", limit=12, expected_frequency="monthly")
    second = await client.series("M2SL", limit=12, expected_frequency="monthly")
    await client.series("M2SL", limit=24, expected_frequency="monthly")

    assert first["observations"][0]["value"] == 22000.0
    assert first["cache"]["status"] == "fresh"
    assert first["cache"]["ttlSeconds"] == 86400
    assert second["cache"]["ageSeconds"] >= 0
    assert len(calls) == 3  # metadata reused; the different observation limit has its own cache key


@pytest.mark.asyncio
async def test_fred_uses_stale_cache_when_unconfigured(tmp_path: Path, monkeypatch) -> None:
    configured = FredClient(tmp_path, api_key="test-key")

    async def fake_request(endpoint: str, params: dict) -> dict:
        if endpoint == "series":
            return {"seriess": [{"id": "UNRATE", "frequency": "Monthly"}]}
        return {"observations": [{"date": "2026-08-01", "value": "4.2"}]}

    monkeypatch.setattr(configured, "_request", fake_request)
    await configured.series("UNRATE", expected_frequency="monthly")

    unconfigured = FredClient(tmp_path, api_key="")
    cached = await unconfigured.series("UNRATE", expected_frequency="monthly")
    assert cached["observations"][0]["value"] == 4.2
    assert cached["cache"]["status"] == "fresh"


def test_snapshot_row_computes_year_over_year_change() -> None:
    spec = FredSeriesSpec("M2SL", "M2", "liquidity", "Money growth", "yoy_pct", "monthly")
    payload = {
        "observations": [
            {"date": "2026-08-01", "value": 110.0},
            {"date": "2026-07-01", "value": 109.0},
            {"date": "2025-08-01", "value": 100.0},
        ],
        "units": "Billions",
        "sourceLastUpdatedAt": "2026-09-01",
        "sourceUrl": "https://fred.stlouisfed.org/series/M2SL",
        "cache": {
            "status": "fresh",
            "fetchedAt": datetime.now(timezone.utc).isoformat(),
            "refreshAfter": datetime.now(timezone.utc).isoformat(),
        },
    }
    row = _snapshot_row(spec, payload)
    assert row["value"] == 10.0
    assert row["nativeValue"] == 110.0
    assert row["changeUnit"] == "percent_yoy"
    assert row["updateSchedule"]["estimatedNextObservationDate"] == "2026-09-01"
    assert row["updateSchedule"]["estimateOnly"] is True


@pytest.mark.asyncio
async def test_fred_http_errors_do_not_expose_api_key(tmp_path: Path, monkeypatch) -> None:
    client = FredClient(tmp_path, api_key="secret-key")

    class Response:
        status_code = 400
        is_error = True

    class HttpClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, *args, **kwargs):
            return Response()

    monkeypatch.setattr("copenet.core.market.fred.httpx.AsyncClient", lambda **kwargs: HttpClient())
    with pytest.raises(RuntimeError, match="FRED returned HTTP 400") as raised:
        await client._request("series", {"api_key": "secret-key"})
    assert "secret-key" not in str(raised.value)
