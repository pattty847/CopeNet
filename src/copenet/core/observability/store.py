"""Durable operator settings and bounded trace reads for Observability."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from copenet.core._json_store import read_json, write_json_atomic


# Retention for the trace directory. Lifecycle tracing is unconditional now, so
# the writer can no longer be assumed to be off — the directory needs a ceiling.
# Pruning is oldest-first by modification time and runs at orchestrator startup.
TRACE_RETENTION_MAX_BYTES = 256 * 1024 * 1024
TRACE_RETENTION_MAX_FILES = 2_000


@dataclass(frozen=True)
class ObservabilitySettings:
    """Runtime-adjustable trace capture settings.

    Run records, transcripts, and the lifecycle trace tier remain available
    regardless of this flag. Debug capture adds the payload-heavy tier —
    sanitized model-input snapshots, reasoning content, and tool result bodies —
    for runs started after the setting is enabled.
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
            "lifecycleCapture": True,
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

    def _trace_files(self) -> list[Path]:
        if not self._trace_root.exists():
            return []
        return [path for path in self._trace_root.glob("*.jsonl") if path.is_file()]

    def trace_storage_stats(self) -> dict[str, int]:
        """Return how much disk the run trace directory currently holds."""
        files = self._trace_files()
        total = 0
        for path in files:
            try:
                total += path.stat().st_size
            except OSError:
                continue
        return {"fileCount": len(files), "totalBytes": total}

    def prune_traces(
        self,
        *,
        max_total_bytes: int = TRACE_RETENTION_MAX_BYTES,
        max_files: int = TRACE_RETENTION_MAX_FILES,
    ) -> dict[str, int]:
        """Delete oldest trace files until the directory is under both ceilings."""
        entries: list[tuple[float, int, Path]] = []
        for path in self._trace_files():
            try:
                stat = path.stat()
            except OSError:
                continue
            entries.append((stat.st_mtime, stat.st_size, path))
        entries.sort(key=lambda item: item[0])
        total = sum(size for _, size, _ in entries)
        removed = 0
        freed = 0
        index = 0
        while index < len(entries) and (total > max_total_bytes or len(entries) - removed > max_files):
            _, size, path = entries[index]
            index += 1
            try:
                path.unlink()
            except OSError:
                continue
            total -= size
            freed += size
            removed += 1
        return {"removedFileCount": removed, "freedBytes": freed}

    def purge_traces(self) -> dict[str, int]:
        """Delete every stored run trace. Run records and transcripts are untouched."""
        removed = 0
        freed = 0
        for path in self._trace_files():
            try:
                size = path.stat().st_size
                path.unlink()
            except OSError:
                continue
            removed += 1
            freed += size
        return {"removedFileCount": removed, "freedBytes": freed}

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
