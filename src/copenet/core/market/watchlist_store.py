"""Durable store for Patrick's user-curated ticker watchlist — separate from the fixed
dashboard UNIVERSE in universe.py (that's the always-on panel set; this is add/remove-able)."""

from __future__ import annotations

import threading
from pathlib import Path

from copenet.core._json_store import read_json, write_json_atomic


class WatchlistStore:
    """Thread-safe JSON store for a flat, ordered list of {symbol, name} entries."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.RLock()

    def list(self) -> list[dict[str, str]]:
        payload = read_json(self._path, {})
        entries = payload.get("entries") if isinstance(payload, dict) else None
        if not isinstance(entries, list):
            return []
        out: list[dict[str, str]] = []
        for entry in entries:
            if isinstance(entry, dict) and entry.get("symbol"):
                out.append({"symbol": str(entry["symbol"]).upper(), "name": str(entry.get("name") or "")})
        return out

    def add(self, symbol: str, name: str = "") -> list[dict[str, str]]:
        normalized = symbol.strip().upper()
        if not normalized:
            raise ValueError("symbol is required")
        with self._lock:
            entries = self.list()
            if not any(e["symbol"] == normalized for e in entries):
                entries.append({"symbol": normalized, "name": name.strip()})
                write_json_atomic(self._path, {"entries": entries})
            return entries

    def remove(self, symbol: str) -> list[dict[str, str]]:
        normalized = symbol.strip().upper()
        with self._lock:
            entries = [e for e in self.list() if e["symbol"] != normalized]
            write_json_atomic(self._path, {"entries": entries})
            return entries
