"""NASA APOD orchestrator helpers — fetch + persist + public mapping.

`nasa.apod` fetches today's (or a given date's) picture, persists it to the durable
collection, and returns the public record. A same-day cache avoids re-hitting the API
on every Home mount; pass ``refresh=True`` to force a re-fetch.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from copenet.core.nasa import NasaApodError, NasaApodRecord

if TYPE_CHECKING:
    from . import Orchestrator


def fetch_apod(orchestrator: "Orchestrator", *, date: str | None = None, refresh: bool = False) -> dict[str, Any]:
    """Fetch one APOD, persist it, and return the public record."""
    target = (date or "").strip()
    if target and not refresh:
        cached = orchestrator._nasa_store.get(target)
        if cached is not None:
            return _public_apod(cached)

    fetched = orchestrator._nasa_service.fetch(date=target or None)
    if not fetched.get("date"):
        raise NasaApodError("NASA APOD response was missing a date")

    # Cache hit for "today" (no explicit date) once we know the resolved date.
    if not target and not refresh:
        cached = orchestrator._nasa_store.get(str(fetched["date"]))
        if cached is not None:
            return _public_apod(cached)

    record = orchestrator._nasa_store.save(NasaApodRecord.from_json(fetched))
    # Warm the image cache so the Home card serves locally and survives a NASA outage.
    if record.media_type == "image":
        orchestrator._nasa_image_cache.cache(record.date, record.url or record.hdurl or "")
    return _public_apod(record)


def list_apods(orchestrator: "Orchestrator", *, limit: int = 60) -> list[dict[str, Any]]:
    """List collected APOD records, newest day first."""
    return [_public_apod(record) for record in orchestrator._nasa_store.list(limit=limit)]


def apod_image_path(orchestrator: "Orchestrator", date: str):
    """Return a servable local image path for a date, caching lazily on first request."""
    key = (date or "").strip()
    if not key:
        return None
    cached = orchestrator._nasa_image_cache.get(key)
    if cached is not None:
        return cached
    record = orchestrator._nasa_store.get(key)
    if record is None or record.media_type != "image":
        return None
    return orchestrator._nasa_image_cache.cache(key, record.url or record.hdurl or "")


def _public_apod(record: NasaApodRecord) -> dict[str, Any]:
    return {
        "date": record.date,
        "title": record.title,
        "explanation": record.explanation,
        "url": record.url,
        "hdUrl": record.hdurl,
        "thumbnailUrl": record.thumbnail_url,
        "cachedUrl": f"/nasa/apod/image/{record.date}" if record.media_type == "image" and record.date else None,
        "mediaType": record.media_type,
        "copyright": record.copyright,
        "serviceVersion": record.service_version,
        "createdAt": record.created_at,
        "updatedAt": record.updated_at,
    }
