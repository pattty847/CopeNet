"""Durable operator-level store for Market Monitor data."""

from __future__ import annotations

import json
from pathlib import Path
import threading
from typing import Any

from copenet.core._json_store import read_json, write_json_atomic

from .models import DashboardPayload, MarketBar


class MarketStore:
    """Thread-safe JSON store for bars, signals, and the latest dashboard."""

    def __init__(self, root_dir: Path) -> None:
        self._root = root_dir
        self._root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def save_bars(self, symbol: str, timeframe: str, bars: list[MarketBar]) -> None:
        path = self._bars_path(symbol, timeframe)
        payload = {"symbol": symbol.upper(), "timeframe": timeframe, "bars": [bar.__dict__ for bar in bars]}
        with self._lock:
            write_json_atomic(path, payload)

    def load_bars(self, symbol: str, timeframe: str) -> list[MarketBar]:
        payload = read_json(self._bars_path(symbol, timeframe), {})
        rows = payload.get("bars") if isinstance(payload, dict) else None
        if not isinstance(rows, list):
            return []
        bars: list[MarketBar] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            try:
                bars.append(
                    MarketBar(
                        t=int(row.get("t") or 0),
                        o=float(row.get("o") or 0),
                        h=float(row.get("h") or 0),
                        l=float(row.get("l") or 0),
                        c=float(row.get("c") or 0),
                        v=int(row.get("v") or 0),
                    )
                )
            except (TypeError, ValueError):
                continue
        return bars

    def save_signals(self, symbol: str, signals: dict[str, Any]) -> None:
        with self._lock:
            write_json_atomic(self._signals_path(symbol), {"symbol": symbol.upper(), "signals": signals})

    def load_signals(self, symbol: str) -> dict[str, Any]:
        payload = read_json(self._signals_path(symbol), {})
        signals = payload.get("signals") if isinstance(payload, dict) else None
        return dict(signals) if isinstance(signals, dict) else {}

    def save_dashboard(self, dashboard: DashboardPayload) -> None:
        with self._lock:
            write_json_atomic(self._root / "latest-dashboard.json", dashboard.to_wire())

    def load_dashboard(self) -> DashboardPayload:
        payload = read_json(self._root / "latest-dashboard.json", {})
        if not isinstance(payload, dict) or not payload:
            return DashboardPayload.empty(as_of="as of no market refresh yet")
        return _dashboard_from_wire(payload)

    def load_dashboard_wire(self) -> dict[str, Any]:
        payload = read_json(self._root / "latest-dashboard.json", {})
        if isinstance(payload, dict) and payload:
            return payload
        return DashboardPayload.empty(as_of="as of no market refresh yet").to_wire()

    def _bars_path(self, symbol: str, timeframe: str) -> Path:
        return self._root / "bars" / f"{symbol.upper()}-{timeframe}.json"

    def _signals_path(self, symbol: str) -> Path:
        return self._root / "signals" / f"{symbol.upper()}.json"


def _dashboard_from_wire(payload: dict[str, Any]) -> DashboardPayload:
    # Keep the store permissive: the canonical persisted shape is the wire dict.
    # For callers that need a DTO, rehydrate through JSON into empty panels and
    # preserve exact payload via monkey-patched serializer.
    dashboard = DashboardPayload.empty(as_of=str(payload.get("asOf") or "as of no market refresh yet"))
    dashboard.to_wire = lambda: json.loads(json.dumps(payload))  # type: ignore[method-assign]
    return dashboard
