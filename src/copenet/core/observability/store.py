"""Durable operator settings and bounded trace reads for Observability."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from copenet.core._json_store import read_json, write_json_atomic


@dataclass(frozen=True)
class ObservabilitySettings:
    """Runtime-adjustable trace capture settings.

    Run records and transcripts remain available regardless of this flag.
    Debug capture adds the per-run JSONL event stream and sanitized model-input
    snapshots for runs started after the setting is enabled.
    """

    debug_capture: bool = False

    @classmethod
    def from_json(cls, raw: dict[str, Any], *, default_debug_capture: bool = False) -> "ObservabilitySettings":
        value = raw.get("debugCapture") if "debugCapture" in raw else raw.get("debug_capture")
        return cls(debug_capture=bool(value) if value is not None else default_debug_capture)

    def to_json(self) -> dict[str, Any]:
        return {"debugCapture": self.debug_capture}

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "debugCapture": self.debug_capture,
            "captureScope": "subsequent_runs",
            "storage": "local",
        }


class ObservabilityStore:
    """Own observability settings and safe reads from the run trace directory."""

    def __init__(self, *, settings_path: Path, trace_root: Path, default_debug_capture: bool = False) -> None:
        self._settings_path = settings_path
        self._trace_root = trace_root
        self._default_debug_capture = default_debug_capture

    def load_settings(self) -> ObservabilitySettings:
        raw = read_json(self._settings_path, {})
        return ObservabilitySettings.from_json(
            raw if isinstance(raw, dict) else {},
            default_debug_capture=self._default_debug_capture,
        )

    @property
    def trace_root(self) -> Path:
        return self._trace_root

    def update_settings(self, *, debug_capture: bool) -> ObservabilitySettings:
        settings = ObservabilitySettings(debug_capture=debug_capture)
        write_json_atomic(self._settings_path, settings.to_json())
        return settings

    def trace_path_for(self, run_id: str) -> Path:
        safe_run_id = "".join(ch for ch in run_id if ch.isalnum() or ch in ("-", "_", ".")).strip()
        if not safe_run_id or safe_run_id != run_id:
            raise ValueError("invalid run_id")
        return self._trace_root / f"{safe_run_id}.jsonl"

    def list_trace_events(self, run_id: str, *, limit: int = 2_000) -> list[dict[str, Any]]:
        if limit <= 0:
            return []
        path = self.trace_path_for(run_id)
        if not path.exists():
            return []
        rows: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines()[-limit:]:
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                rows.append(parsed)
        return rows
