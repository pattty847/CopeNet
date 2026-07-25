"""Thin TMDB API v3 client with secret-safe errors and bounded retry handling."""

from __future__ import annotations

import json
import os
import time
from typing import Any
from urllib import error, parse, request


_API_ROOT = "https://api.themoviedb.org/3"


class TmdbError(RuntimeError):
    """Raised for missing configuration or a failed TMDB request."""


class TmdbClient:
    def __init__(self, *, access_token: str | None = None, api_key: str | None = None) -> None:
        self._access_token = (access_token or os.environ.get("TMDB_ACCESS_TOKEN", "")).strip()
        self._api_key = (api_key or os.environ.get("TMDB_API_KEY", "")).strip()

    @property
    def configured(self) -> bool:
        return bool(self._access_token or self._api_key)

    def search_multi(self, query: str) -> list[dict[str, Any]]:
        payload = self._get("/search/multi", {"query": query, "include_adult": "false"})
        results = payload.get("results")
        return [item for item in results if isinstance(item, dict)] if isinstance(results, list) else []

    def details(self, media_type: str, tmdb_id: int) -> dict[str, Any]:
        if media_type not in {"movie", "tv"}:
            raise TmdbError(f"unsupported TMDB media type: {media_type}")
        return self._get(
            f"/{media_type}/{int(tmdb_id)}",
            {"append_to_response": "credits,keywords"},
        )

    def recommendations(self, media_type: str, tmdb_id: int) -> list[dict[str, Any]]:
        if media_type not in {"movie", "tv"}:
            return []
        payload = self._get(f"/{media_type}/{int(tmdb_id)}/recommendations", {})
        results = payload.get("results")
        return [item for item in results if isinstance(item, dict)] if isinstance(results, list) else []

    def _get(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        if not self.configured:
            raise TmdbError("TMDB is not configured; set TMDB_ACCESS_TOKEN or TMDB_API_KEY in .env")
        query = dict(params)
        if self._api_key and not self._access_token:
            query["api_key"] = self._api_key
        url = f"{_API_ROOT}{path}"
        if query:
            url += "?" + parse.urlencode(query)
        headers = {"Accept": "application/json"}
        if self._access_token:
            headers["Authorization"] = f"Bearer {self._access_token}"
        req = request.Request(url, headers=headers)
        for attempt in range(3):
            try:
                with request.urlopen(req, timeout=20.0) as response:
                    body = response.read()
                break
            except error.HTTPError as exc:
                if exc.code == 429 and attempt < 2:
                    retry_after = min(float(exc.headers.get("Retry-After", "1") or 1), 5.0)
                    time.sleep(max(retry_after, 0.25))
                    continue
                raise TmdbError(f"TMDB request failed with HTTP {exc.code} for {path}") from exc
            except error.URLError as exc:
                raise TmdbError(f"TMDB is unreachable for {path}: {exc.reason}") from exc
        try:
            payload = json.loads(body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise TmdbError(f"TMDB returned malformed JSON for {path}") from exc
        if not isinstance(payload, dict):
            raise TmdbError(f"TMDB returned an unexpected response for {path}")
        return payload
