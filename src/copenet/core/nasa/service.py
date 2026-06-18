"""NASA APOD fetch service — thin wrapper over the planetary/apod endpoint.

Reads ``NASA_API_KEY`` from the environment (loaded from `.env` at startup). Uses
the stdlib HTTP client to stay dependency-free, mirroring ``core/web_ingest.py``.
"""

from __future__ import annotations

import json
import os
from typing import Any
from urllib import error, parse, request

_APOD_ENDPOINT = "https://api.nasa.gov/planetary/apod"


class NasaApodError(RuntimeError):
    """Raised when the APOD endpoint cannot be reached or returns an error."""


class NasaApodService:
    """Fetches normalized APOD records from api.nasa.gov."""

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = (api_key or os.environ.get("NASA_API_KEY", "")).strip()

    @property
    def configured(self) -> bool:
        return bool(self._api_key)

    def fetch(self, *, date: str | None = None) -> dict[str, Any]:
        """Fetch one APOD (today by default) and return normalized fields."""
        if not self._api_key:
            raise NasaApodError("NASA_API_KEY is not set")
        query: dict[str, str] = {"api_key": self._api_key, "thumbs": "true"}
        if date:
            query["date"] = date.strip()
        url = f"{_APOD_ENDPOINT}?{parse.urlencode(query)}"
        req = request.Request(url, headers={"Accept": "application/json"})
        try:
            with request.urlopen(req, timeout=15.0) as response:
                body = response.read()
        except error.HTTPError as exc:
            raise NasaApodError(f"NASA APOD HTTP {exc.code}") from exc
        except error.URLError as exc:
            raise NasaApodError(f"NASA APOD unreachable: {exc.reason}") from exc
        try:
            raw = json.loads(body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise NasaApodError("NASA APOD returned malformed JSON") from exc
        if not isinstance(raw, dict):
            raise NasaApodError("NASA APOD returned an unexpected shape")
        return _normalize(raw)


def _normalize(raw: dict[str, Any]) -> dict[str, Any]:
    media_type = str(raw.get("media_type") or "image").strip().lower()
    if media_type not in {"image", "video"}:
        media_type = "image"
    return {
        "date": str(raw.get("date") or "").strip(),
        "title": str(raw.get("title") or "").strip(),
        "explanation": str(raw.get("explanation") or "").strip(),
        "url": str(raw.get("url") or "").strip(),
        "hdurl": _opt(raw.get("hdurl")),
        "thumbnail_url": _opt(raw.get("thumbnail_url")),
        "media_type": media_type,
        "copyright": _opt(raw.get("copyright")),
        "service_version": _opt(raw.get("service_version")),
    }


def _opt(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
