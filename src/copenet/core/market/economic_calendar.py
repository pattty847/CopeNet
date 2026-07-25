"""Trading Economics calendar adapter with a durable stale-on-error cache."""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

from copenet.core._json_store import read_json, write_json_atomic


_API_ROOT = "https://api.tradingeconomics.com"
_CACHE_MAX_AGE = timedelta(minutes=15)
_DEFAULT_DAYS = 7
_MAX_DAYS = 14


def trading_economics_api_key() -> str | None:
    value = os.environ.get("TRADING_ECONOMICS_API_KEY", "").strip()
    return value or None


async def load_economic_calendar(
    store_root: Path,
    *,
    days: int = _DEFAULT_DAYS,
    refresh: bool = False,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Return a normalized US calendar, cached locally and honest when unconfigured.

    The cache survives provider failures so the morning surface can show stale events instead
    of disappearing. Values from the external API are normalized once at this trust boundary.
    """
    current = now or datetime.now(timezone.utc)
    window_days = max(1, min(int(days), _MAX_DAYS))
    path = store_root / "economic-calendar" / "latest.json"
    cached = read_json(path, None)
    key = trading_economics_api_key()
    if not key:
        return _unconfigured(cached)
    if not refresh and _cache_is_fresh(cached, current):
        return _with_status(cached, configured=True, stale=False)

    start = current.date()
    end = start + timedelta(days=window_days)
    url = f"{_API_ROOT}/calendar/country/{quote('United States')}/{start.isoformat()}/{end.isoformat()}"
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            response = await client.get(
                url,
                params={"c": key, "values": "true", "f": "json"},
                headers={"Accept": "application/json", "User-Agent": "CopeNet/market-calendar"},
            )
            response.raise_for_status()
            raw = response.json()
        events = _normalize_events(raw, start=start, end=end)
        payload = {
            "configured": True,
            "provider": "Trading Economics",
            "sourceUrl": "https://tradingeconomics.com/united-states/calendar",
            "retrievedAt": _iso(current),
            "windowStart": start.isoformat(),
            "windowEnd": end.isoformat(),
            "stale": False,
            "events": events,
        }
        write_json_atomic(path, payload)
        return payload
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        if isinstance(cached, dict) and cached.get("events") is not None:
            payload = _with_status(cached, configured=True, stale=True)
            payload["error"] = "Calendar refresh failed; showing the last successful snapshot."
            return payload
        return {
            "configured": True,
            "provider": "Trading Economics",
            "sourceUrl": "https://tradingeconomics.com/united-states/calendar",
            "retrievedAt": _iso(current),
            "windowStart": start.isoformat(),
            "windowEnd": end.isoformat(),
            "stale": False,
            "events": [],
            "error": f"Trading Economics calendar unavailable ({type(exc).__name__}).",
        }


def _normalize_events(raw: Any, *, start: date, end: date) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        raise ValueError("calendar response must be a list")
    events: list[dict[str, Any]] = []
    for row in raw:
        if not isinstance(row, dict):
            continue
        event_at = _parse_datetime(row.get("Date"))
        name = str(row.get("Event") or row.get("Category") or "").strip()
        if event_at is None or not name or not (start <= event_at.date() <= end):
            continue
        importance = _int(row.get("Importance"), minimum=1, maximum=3) or 1
        if importance < 2:
            continue
        events.append(
            {
                "id": str(row.get("CalendarId") or f"{event_at.isoformat()}-{name}"),
                "date": _iso(event_at),
                "country": str(row.get("Country") or "United States"),
                "event": name,
                "category": str(row.get("Category") or ""),
                "importance": importance,
                "actual": _optional_text(row.get("Actual")),
                "forecast": _optional_text(row.get("Forecast")),
                "previous": _optional_text(row.get("Previous")),
                "revised": _optional_text(row.get("Revised")),
                "unit": _optional_text(row.get("Unit")),
                "reference": _optional_text(row.get("Reference")),
                "source": _optional_text(row.get("Source")),
                "sourceUrl": _optional_http_url(row.get("SourceURL")),
            }
        )
    events.sort(key=lambda item: (item["date"], -item["importance"], item["event"]))
    return events


def _unconfigured(cached: Any) -> dict[str, Any]:
    if isinstance(cached, dict) and cached.get("events") is not None:
        payload = _with_status(cached, configured=False, stale=True)
        payload["error"] = "Add TRADING_ECONOMICS_API_KEY to refresh this calendar."
        return payload
    today = datetime.now(timezone.utc).date()
    return {
        "configured": False,
        "provider": "Trading Economics",
        "sourceUrl": "https://tradingeconomics.com/united-states/calendar",
        "windowStart": today.isoformat(),
        "windowEnd": (today + timedelta(days=_DEFAULT_DAYS)).isoformat(),
        "stale": False,
        "events": [],
    }


def _cache_is_fresh(payload: Any, now: datetime) -> bool:
    if not isinstance(payload, dict):
        return False
    retrieved = _parse_datetime(payload.get("retrievedAt"))
    return retrieved is not None and now - retrieved <= _CACHE_MAX_AGE


def _with_status(payload: dict[str, Any], *, configured: bool, stale: bool) -> dict[str, Any]:
    result = dict(payload)
    result["configured"] = configured
    result["stale"] = stale
    return result


def _parse_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=parsed.tzinfo or timezone.utc).astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _optional_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _optional_http_url(value: Any) -> str | None:
    text = _optional_text(value)
    return text if text and text.startswith(("http://", "https://")) else None


def _int(value: Any, *, minimum: int, maximum: int) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return max(minimum, min(parsed, maximum))
