"""Scan boundary validation, source catalogue, and strictly future schedules."""
from __future__ import annotations

import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

SOURCES = [
    {"id": "prices", "label": "Prices & technical screens", "scope": "asset"},
    {"id": "sec", "label": "SEC · Form 4, 8-K & 144", "scope": "asset"},
    {"id": "financials", "label": "SEC revenue & diluted EPS", "scope": "asset"},
    {"id": "rates", "label": "U.S. Treasury curve", "scope": "global"},
    {"id": "calendar", "label": "U.S. economic calendar", "scope": "global"},
]


def symbols(value, field: str) -> list[str]:
    if not isinstance(value, list) or len(value) > 1000:
        raise ValueError(f"{field} must be a list of at most 1000 symbols")
    if any(not isinstance(item, str) or not re.fullmatch(r"[A-Za-z0-9^][A-Za-z0-9.^=\-]{0,24}", item.strip()) for item in value):
        raise ValueError(f"{field} contains an invalid symbol")
    return list(dict.fromkeys(item.strip().upper() for item in value))


def validate_scan(raw: dict) -> dict:
    if not isinstance(raw, dict):
        raise ValueError("scan must be an object")
    name = raw.get("name", "")
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80:
        raise ValueError("Scan name must be 1–80 characters")
    identifier = raw.get("id", "")
    if not isinstance(identifier, str) or (identifier and not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", identifier)):
        raise ValueError("Invalid scan id")
    revision = raw.get("revision", 0)
    if type(revision) is not int or revision < 0:
        raise ValueError("Invalid scan revision")
    result = {"id": identifier, "revision": revision, "name": name.strip()}
    for key in ("enabled", "includeUniverse", "publishBrief", "interpret"):
        value = raw.get(key, key == "enabled")
        if type(value) is not bool:
            raise ValueError(f"{key} must be true or false")
        result[key] = value
    for key in ("symbols", "excludeSymbols"):
        result[key] = symbols(raw.get(key, []), key)
    lists = raw.get("watchlists", [])
    if not isinstance(lists, list) or len(lists) > 30 or any(not isinstance(item, str) or not 1 <= len(item) <= 30 for item in lists):
        raise ValueError("watchlists must contain named watchlists")
    result["watchlists"] = list(dict.fromkeys(lists))
    sources = raw.get("sources", [])
    if not isinstance(sources, list) or not sources or any(not isinstance(item, str) or item not in {s["id"] for s in SOURCES} for item in sources):
        raise ValueError("Select at least one supported source")
    result["sources"] = list(dict.fromkeys(sources))
    times = raw.get("times", ["09:45"])
    if not isinstance(times, list) or not 1 <= len(times) <= 12 or any(not isinstance(item, str) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", item) for item in times):
        raise ValueError("Choose 1–12 times in HH:MM format")
    result["times"] = sorted(set(times))
    days = raw.get("days", list(range(7)))
    if not isinstance(days, list) or not days or any(type(day) is not int or day not in range(7) for day in days):
        raise ValueError("Choose days from 0 (Monday) through 6 (Sunday)")
    result["days"] = sorted(set(days))
    zone = raw.get("timezone", "America/New_York")
    try:
        if not isinstance(zone, str):
            raise ValueError()
        ZoneInfo(zone)
    except (ValueError, ZoneInfoNotFoundError):
        raise ValueError("Choose a valid IANA timezone") from None
    result["timezone"] = zone
    if result["publishBrief"] and (identifier != "morning" or not result["includeUniverse"] or not {"prices", "sec"}.issubset(sources) or result["excludeSymbols"]):
        raise ValueError("Only the complete morning scan can publish the market briefing; turn publishing off for a focused scan")
    if result["interpret"] and not result["publishBrief"]:
        raise ValueError("Whole-market interpretation requires the complete morning briefing")
    return result


def local_timezone() -> str:
    candidate = os.environ.get("TZ", "")
    if not candidate:
        path = str(Path("/etc/localtime").resolve())
        candidate = path.split("zoneinfo/")[-1] if "zoneinfo/" in path else "America/New_York"
    try:
        return ZoneInfo(candidate).key
    except (ValueError, ZoneInfoNotFoundError):
        return "America/New_York"


def default_scan(watchlists: list[dict]) -> dict:
    """One-time env migration; persisted definitions own all subsequent schedule edits."""
    time = os.environ.get("COPNET_MARKET_BRIEF_TIME", "09:45").strip()
    if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", time):
        time = "09:45"
    return validate_scan({"id": "morning", "revision": 1, "name": "Morning overview", "enabled": True,
        "includeUniverse": True, "symbols": [], "watchlists": [w["name"] for w in watchlists if w["role"] != "context"],
        "excludeSymbols": [], "sources": ["prices", "sec"], "times": [time], "days": list(range(7)),
        "timezone": local_timezone(), "publishBrief": True, "interpret": True})


def next_run_at(scan: dict, now: datetime) -> datetime | None:
    if not scan["enabled"]:
        return None
    zone = ZoneInfo(scan["timezone"])
    local = now.astimezone(zone)
    for offset in range(9):
        day = local.date() + timedelta(days=offset)
        if day.weekday() not in scan["days"]:
            continue
        for clock in scan["times"]:
            hour, minute = map(int, clock.split(":"))
            candidate = datetime(day.year, day.month, day.day, hour, minute, tzinfo=zone)
            utc = candidate.astimezone(timezone.utc)
            # Nonexistent spring-forward times are skipped; repeated fall times fire once.
            if utc.astimezone(zone).replace(tzinfo=None) != candidate.replace(tzinfo=None):
                continue
            if utc > now.astimezone(timezone.utc):
                return utc
    return None
