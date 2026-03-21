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
