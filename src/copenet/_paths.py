"""Default data paths for CopeNet (configurable via env or constructor args)."""

from __future__ import annotations

import os
from pathlib import Path


def default_sessions_dir() -> Path:
    """Return default sessions root: COPNET_DATA_DIR/sessions or ~/.copenet/sessions."""
    base = os.environ.get("COPNET_DATA_DIR", "").strip()
    if base:
        return Path(base).expanduser() / "sessions"
    return Path.home() / ".copenet" / "sessions"


def default_run_logs_dir() -> Path:
    """Return default per-run trace root: COPNET_DATA_DIR/logs/runs or ~/.copenet/logs/runs."""
    base = os.environ.get("COPNET_DATA_DIR", "").strip()
    if base:
        return Path(base).expanduser() / "logs" / "runs"
    return Path.home() / ".copenet" / "logs" / "runs"
