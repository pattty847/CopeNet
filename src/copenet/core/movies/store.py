"""Atomic local storage for the personal Movie Lab."""

from __future__ import annotations

from pathlib import Path
import threading
from typing import Any

from copenet.core._json_store import read_json, write_json_atomic


def _empty_state() -> dict[str, Any]:
    return {
        "version": 1,
        "source": None,
        "watched": [],
        "matches": {},
        "catalog": {},
        "recommendations": [],
    }


class MovieLabStore:
    """Thread-safe single-file store; sufficient for a personal catalog and easy to inspect."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.RLock()

    @property
    def path(self) -> Path:
        return self._path

    def state(self) -> dict[str, Any]:
        with self._lock:
            raw = read_json(self._path, {})
        state = _empty_state()
        if isinstance(raw, dict):
            state.update(raw)
        for key, fallback in (("watched", []), ("matches", {}), ("catalog", {}), ("recommendations", [])):
            if not isinstance(state.get(key), type(fallback)):
                state[key] = fallback
        return state

    def replace_watched(self, watched: list[dict[str, Any]], *, source: Path) -> dict[str, Any]:
        with self._lock:
            state = self.state()
            valid_rows = {str(item["sourceRow"]) for item in watched}
            state["source"] = str(source.expanduser().resolve())
            state["watched"] = watched
            state["matches"] = {
                row: match for row, match in state["matches"].items() if row in valid_rows
            }
            self._save(state)
        return state

    def save_match(self, source_row: int, match: dict[str, Any]) -> None:
        with self._lock:
            state = self.state()
            state["matches"][str(source_row)] = match
            self._save(state)

    def save_catalog_item(self, item: dict[str, Any]) -> None:
        key = catalog_key(str(item["mediaType"]), int(item["tmdbId"]))
        with self._lock:
            state = self.state()
            state["catalog"][key] = item
            self._save(state)

    def save_recommendations(self, recommendations: list[dict[str, Any]]) -> None:
        with self._lock:
            state = self.state()
            state["recommendations"] = recommendations
            self._save(state)

    def prune_catalog_to_matches(self) -> None:
        with self._lock:
            state = self.state()
            active_keys = {
                catalog_key(str(selected["mediaType"]), int(selected["tmdbId"]))
                for match in state["matches"].values()
                if isinstance(match, dict) and isinstance((selected := match.get("selected")), dict)
            }
            state["catalog"] = {
                key: item for key, item in state["catalog"].items() if key in active_keys
            }
            self._save(state)

    def _save(self, state: dict[str, Any]) -> None:
        write_json_atomic(self._path, state)


def catalog_key(media_type: str, tmdb_id: int) -> str:
    return f"{media_type}:{tmdb_id}"
