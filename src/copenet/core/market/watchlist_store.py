"""Durable store for Patrick's user-curated ticker watchlists — separate from the fixed
dashboard UNIVERSE in universe.py (that's the always-on panel set; these are add/remove-able).

Multiple named lists (TradingView-style tabs). Persisted shape:
    {"lists": [{"name": "Default", "entries": [{"symbol", "name"}, ...]}, ...], "active": "Default"}
The pre-multi-list flat shape ({"entries": [...]}) migrates to a single "Default" list on read.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from copenet.core._json_store import read_json, write_json_atomic

DEFAULT_LIST_NAME = "Default"
_MAX_LIST_NAME_LEN = 30
_MAX_LISTS = 20


class WatchlistStore:
    """Thread-safe JSON store for named, ordered watchlists of {symbol, name} entries."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.RLock()

    # ---------- state ----------

    def state(self) -> dict[str, Any]:
        """{"lists": [names...], "active": name, "entries": entries-of-active-list}."""
        payload = self._load()
        return {
            "lists": [wl["name"] for wl in payload["lists"]],
            "active": payload["active"],
            "entries": self._entries_of(payload, payload["active"]),
        }

    def list(self, list_name: str | None = None) -> list[dict[str, str]]:
        payload = self._load()
        return self._entries_of(payload, (list_name or payload["active"]).strip())

    # ---------- entries ----------

    def add(self, symbol: str, name: str = "", list_name: str | None = None) -> list[dict[str, str]]:
        normalized = symbol.strip().upper()
        if not normalized:
            raise ValueError("symbol is required")
        with self._lock:
            payload = self._load()
            target = self._find_list(payload, list_name or payload["active"])
            if not any(e["symbol"] == normalized for e in target["entries"]):
                target["entries"].append({"symbol": normalized, "name": name.strip()})
                self._save(payload)
            return list(target["entries"])

    def remove(self, symbol: str, list_name: str | None = None) -> list[dict[str, str]]:
        normalized = symbol.strip().upper()
        with self._lock:
            payload = self._load()
            target = self._find_list(payload, list_name or payload["active"])
            target["entries"] = [e for e in target["entries"] if e["symbol"] != normalized]
            self._save(payload)
            return list(target["entries"])

    # ---------- lists ----------

    def create_list(self, name: str) -> dict[str, Any]:
        cleaned = self._valid_name(name)
        with self._lock:
            payload = self._load()
            if any(wl["name"].lower() == cleaned.lower() for wl in payload["lists"]):
                raise ValueError(f"a watchlist named '{cleaned}' already exists")
            if len(payload["lists"]) >= _MAX_LISTS:
                raise ValueError(f"watchlist limit reached ({_MAX_LISTS})")
            payload["lists"].append({"name": cleaned, "entries": []})
            payload["active"] = cleaned
            self._save(payload)
        return self.state()

    def replace_list(self, name: str, entries: list[dict[str, str]]) -> dict[str, Any]:
        """Upsert a whole list by name — creates it when absent, overwrites its entries when
        present. Used by the Webull import, which re-pulls the broker's lists wholesale."""
        cleaned = self._valid_name(name)
        normalized = [
            {"symbol": str(entry["symbol"]).strip().upper(), "name": str(entry.get("name") or "").strip()}
            for entry in entries
            if isinstance(entry, dict) and str(entry.get("symbol") or "").strip()
        ]
        with self._lock:
            payload = self._load()
            existing = next((wl for wl in payload["lists"] if wl["name"].lower() == cleaned.lower()), None)
            if existing is None:
                if len(payload["lists"]) >= _MAX_LISTS:
                    raise ValueError(f"watchlist limit reached ({_MAX_LISTS})")
                payload["lists"].append({"name": cleaned, "entries": normalized})
            else:
                existing["entries"] = normalized
            self._save(payload)
        return self.state()

    def delete_list(self, name: str) -> dict[str, Any]:
        cleaned = name.strip()
        with self._lock:
            payload = self._load()
            if len(payload["lists"]) <= 1:
                raise ValueError("cannot delete the last watchlist")
            before = len(payload["lists"])
            payload["lists"] = [wl for wl in payload["lists"] if wl["name"] != cleaned]
            if len(payload["lists"]) == before:
                raise ValueError(f"no watchlist named '{cleaned}'")
            if payload["active"] == cleaned:
                payload["active"] = payload["lists"][0]["name"]
            self._save(payload)
        return self.state()

    def select_list(self, name: str) -> dict[str, Any]:
        cleaned = name.strip()
        with self._lock:
            payload = self._load()
            self._find_list(payload, cleaned)  # raises on unknown
            payload["active"] = cleaned
            self._save(payload)
        return self.state()

    # ---------- internals ----------

    def _load(self) -> dict[str, Any]:
        raw = read_json(self._path, {})
        if not isinstance(raw, dict):
            raw = {}
        lists = raw.get("lists")
        if not isinstance(lists, list):
            # Migrate the pre-multi-list flat shape (or an empty file) to one Default list.
            legacy = raw.get("entries") if isinstance(raw.get("entries"), list) else []
            lists = [{"name": DEFAULT_LIST_NAME, "entries": legacy}]
        normalized_lists: list[dict[str, Any]] = []
        for wl in lists:
            if not isinstance(wl, dict) or not str(wl.get("name") or "").strip():
                continue
            entries = []
            for entry in wl.get("entries") or []:
                if isinstance(entry, dict) and entry.get("symbol"):
                    entries.append({"symbol": str(entry["symbol"]).upper(), "name": str(entry.get("name") or "")})
            normalized_lists.append({"name": str(wl["name"]).strip(), "entries": entries})
        if not normalized_lists:
            normalized_lists = [{"name": DEFAULT_LIST_NAME, "entries": []}]
        active = str(raw.get("active") or "").strip()
        if active not in {wl["name"] for wl in normalized_lists}:
            active = normalized_lists[0]["name"]
        return {"lists": normalized_lists, "active": active}

    def _save(self, payload: dict[str, Any]) -> None:
        write_json_atomic(self._path, payload)

    @staticmethod
    def _entries_of(payload: dict[str, Any], list_name: str) -> list[dict[str, str]]:
        for wl in payload["lists"]:
            if wl["name"] == list_name:
                return list(wl["entries"])
        return []

    @staticmethod
    def _find_list(payload: dict[str, Any], list_name: str) -> dict[str, Any]:
        cleaned = list_name.strip()
        for wl in payload["lists"]:
            if wl["name"] == cleaned:
                return wl
        raise ValueError(f"no watchlist named '{cleaned}'")

    @staticmethod
    def _valid_name(name: str) -> str:
        cleaned = name.strip()
        if not cleaned:
            raise ValueError("watchlist name is required")
        if len(cleaned) > _MAX_LIST_NAME_LEN:
            raise ValueError(f"watchlist name is too long (max {_MAX_LIST_NAME_LEN} chars)")
        return cleaned
