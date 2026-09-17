"""FRED data boundary with durable, stale-on-error caching and update metadata."""

from __future__ import annotations

import asyncio
import calendar
import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx

from copenet.core._json_store import read_json, write_json_atomic
from .fred_catalog import CURATED_FRED_SERIES, FredSeriesSpec


FRED_API_ROOT = "https://api.stlouisfed.org/fred"
_SEARCH_TTL = timedelta(days=7)
_FREQUENCY_TTLS = {
    "daily": timedelta(hours=6),
    "weekly": timedelta(hours=12),
    "monthly": timedelta(hours=24),
    "quarterly": timedelta(days=3),
    "annual": timedelta(days=7),
    "unknown": timedelta(hours=12),
}


def fred_api_key() -> str | None:
    value = os.environ.get("FRED_API_KEY", "").strip()
    return value or None


class FredClient:
    def __init__(self, cache_root: Path, *, api_key: str | None = None, timeout: float = 15.0) -> None:
        self.cache_root = cache_root
        self.api_key = (api_key or fred_api_key() or "").strip()
        self.timeout = timeout

    async def search(self, query: str, *, limit: int = 10, refresh: bool = False) -> dict[str, Any]:
        text = query.strip()
        if not text:
            raise ValueError("query is required")
        limit = max(1, min(int(limit), 25))
        params = {"search_text": text, "limit": limit, "order_by": "search_rank", "sort_order": "desc"}
        return await self._cached_request("series/search", params, ttl=_SEARCH_TTL, refresh=refresh)

    async def series(
        self,
        series_id: str,
        *,
        limit: int = 120,
        observation_start: str | None = None,
        observation_end: str | None = None,
        vintage_date: str | None = None,
        refresh: bool = False,
        expected_frequency: str = "unknown",
    ) -> dict[str, Any]:
        normalized = series_id.strip().upper()
        if not normalized or len(normalized) > 80 or not normalized.replace("_", "").isalnum():
            raise ValueError("seriesId must contain only letters, numbers, or underscores")
        params: dict[str, Any] = {
            "series_id": normalized,
            "limit": max(2, min(int(limit), 5000)),
            "sort_order": "desc",
        }
        if observation_start:
            params["observation_start"] = observation_start
        if observation_end:
            params["observation_end"] = observation_end
        if vintage_date:
            params["vintage_dates"] = vintage_date
        ttl = _FREQUENCY_TTLS.get(expected_frequency.lower(), _FREQUENCY_TTLS["unknown"])
        metadata, observations = await asyncio.gather(
            self._cached_request("series", {"series_id": normalized}, ttl=ttl, refresh=refresh),
            self._cached_request("series/observations", params, ttl=ttl, refresh=refresh),
        )
        series_rows = metadata.get("seriess") or []
        meta = series_rows[0] if series_rows else {"id": normalized}
        rows = [_observation(row) for row in observations.get("observations") or []]
        return {
            "seriesId": normalized,
            "title": meta.get("title"),
            "frequency": meta.get("frequency"),
            "frequencyShort": meta.get("frequency_short"),
            "units": meta.get("units"),
            "unitsShort": meta.get("units_short"),
            "seasonalAdjustment": meta.get("seasonal_adjustment"),
            "observationStart": meta.get("observation_start"),
            "observationEnd": meta.get("observation_end"),
            "sourceLastUpdatedAt": meta.get("last_updated"),
            "notes": meta.get("notes"),
            "observations": rows,
            "cache": observations["cache"],
            "vintageDate": vintage_date,
            "source": "FRED",
            "sourceUrl": f"https://fred.stlouisfed.org/series/{normalized}",
        }

    async def snapshot(self, *, refresh: bool = False) -> dict[str, Any]:
        semaphore = asyncio.Semaphore(6)

        async def load(spec: FredSeriesSpec) -> dict[str, Any]:
            try:
                async with semaphore:
                    payload = await self.series(
                        spec.series_id,
                        limit=_snapshot_limit(spec),
                        refresh=refresh,
                        expected_frequency=spec.expected_frequency,
                    )
                return _snapshot_row(spec, payload)
            except Exception as exc:
                return {**spec.to_wire(), "status": "unavailable", "error": str(exc)}

        rows = await asyncio.gather(*(load(spec) for spec in CURATED_FRED_SERIES))
        groups: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            groups.setdefault(str(row["group"]), []).append(row)
        return {
            "configured": bool(self.api_key),
            "generatedAt": _iso(datetime.now(timezone.utc)),
            "source": "FRED",
            "groups": groups,
            "seriesCount": len(rows),
            "unavailableCount": sum(row.get("status") == "unavailable" for row in rows),
        }

    async def _cached_request(
        self, endpoint: str, params: dict[str, Any], *, ttl: timedelta, refresh: bool
    ) -> dict[str, Any]:
        cache_path = self._cache_path(endpoint, params)
        cached = read_json(cache_path, None)
        now = datetime.now(timezone.utc)
        if cached and not refresh and _parse_time(cached.get("fetchedAt")) + ttl > now:
            return _with_cache(cached["payload"], cached, ttl, now, "fresh")
        if not self.api_key:
            if cached:
                return _with_cache(cached["payload"], cached, ttl, now, "stale")
            raise RuntimeError("FRED is not configured; set FRED_API_KEY")
        request_params = {**params, "api_key": self.api_key, "file_type": "json"}
        try:
            payload = await self._request(endpoint, request_params)
        except Exception:
            if cached:
                return _with_cache(cached["payload"], cached, ttl, now, "stale")
            raise
        record = {"fetchedAt": _iso(now), "payload": payload}
        write_json_atomic(cache_path, record)
        return _with_cache(payload, record, ttl, now, "fresh")

    async def _request(self, endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
        delay = 0.5
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for attempt in range(3):
                response = await client.get(f"{FRED_API_ROOT}/{endpoint}", params=params)
                if response.status_code != 429 and response.status_code < 500:
                    if response.is_error:
                        raise RuntimeError(f"FRED returned HTTP {response.status_code}")
                    payload = response.json()
                    if not isinstance(payload, dict):
                        raise RuntimeError("FRED returned an invalid JSON payload")
                    return payload
                if attempt < 2:
                    await asyncio.sleep(delay)
                    delay *= 2
            raise RuntimeError(f"FRED returned HTTP {response.status_code} after retries")
        raise RuntimeError("FRED request failed")

    def _cache_path(self, endpoint: str, params: dict[str, Any]) -> Path:
        canonical = json.dumps({"endpoint": endpoint, "params": params}, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        return self.cache_root / endpoint.replace("/", "-") / f"{digest}.json"


def _observation(row: dict[str, Any]) -> dict[str, Any]:
    raw = row.get("value")
    try:
        value = None if raw in (None, ".") else float(raw)
    except (TypeError, ValueError):
        value = None
    return {
        "date": row.get("date"),
        "value": value,
        "realtimeStart": row.get("realtime_start"),
        "realtimeEnd": row.get("realtime_end"),
    }


def _snapshot_row(spec: FredSeriesSpec, payload: dict[str, Any]) -> dict[str, Any]:
    observations = [row for row in payload["observations"] if row.get("value") is not None]
    latest = observations[0] if observations else None
    previous = observations[1] if len(observations) > 1 else None
    value = latest["value"] if latest else None
    change = value - previous["value"] if latest and previous else None
    change_unit = "native"
    if spec.transform == "yoy_pct" and latest:
        year_ago = next((row for row in observations[1:] if str(row["date"]) <= _one_year_before(str(latest["date"]))), None)
        if year_ago and year_ago["value"]:
            value = (latest["value"] / year_ago["value"] - 1) * 100
            change = None
            change_unit = "percent_yoy"
    elif spec.transform == "change":
        value = change
        change_unit = "native_change"
    cache = payload["cache"]
    return {
        **spec.to_wire(),
        "status": "available" if latest else "unavailable",
        "value": round(value, 4) if value is not None else None,
        "nativeValue": latest["value"] if latest else None,
        "previousValue": previous["value"] if previous else None,
        "change": round(change, 4) if change is not None else None,
        "changeUnit": change_unit,
        "units": payload.get("units"),
        "observationDate": latest["date"] if latest else None,
        "sourceLastUpdatedAt": payload.get("sourceLastUpdatedAt"),
        "updateSchedule": {
            "expectedFrequency": spec.expected_frequency,
            "estimatedNextObservationDate": _estimated_next_observation(
                latest["date"] if latest else None, spec.expected_frequency
            ),
            "estimateOnly": True,
            "nextCacheRefreshAt": cache.get("refreshAfter"),
        },
        "cache": cache,
        "sourceUrl": payload["sourceUrl"],
    }


def _snapshot_limit(spec: FredSeriesSpec) -> int:
    if spec.transform != "yoy_pct":
        return 3
    return {"weekly": 56, "monthly": 15, "quarterly": 6, "annual": 3}.get(spec.expected_frequency, 370)


def _estimated_next_observation(value: str | None, frequency: str) -> str | None:
    if not value:
        return None
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        return None
    if frequency in {"daily", "weekly"}:
        return (moment + timedelta(days=1 if frequency == "daily" else 7)).date().isoformat()
    months = {"monthly": 1, "quarterly": 3, "annual": 12}.get(frequency)
    if months is None:
        return None
    month_index = moment.month - 1 + months
    year = moment.year + month_index // 12
    month = month_index % 12 + 1
    day = min(moment.day, calendar.monthrange(year, month)[1])
    return moment.replace(year=year, month=month, day=day).date().isoformat()


def _with_cache(payload: dict[str, Any], record: dict[str, Any], ttl: timedelta, now: datetime, status: str) -> dict[str, Any]:
    fetched = _parse_time(record.get("fetchedAt"))
    refresh_after = fetched + ttl
    return {
        **payload,
        "cache": {
            "status": status,
            "fetchedAt": _iso(fetched),
            "ageSeconds": max(0, int((now - fetched).total_seconds())),
            "refreshAfter": _iso(refresh_after),
            "ttlSeconds": int(ttl.total_seconds()),
        },
    }


def _parse_time(value: Any) -> datetime:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)
    except (TypeError, ValueError):
        return datetime.fromtimestamp(0, timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _one_year_before(value: str) -> str:
    try:
        moment = datetime.fromisoformat(value)
        return moment.replace(year=moment.year - 1).date().isoformat()
    except ValueError:
        return ""
