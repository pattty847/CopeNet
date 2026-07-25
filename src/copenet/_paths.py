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


def default_media_dir() -> Path:
    """Return default media asset root: COPNET_DATA_DIR/media or ~/.copenet/media."""
    base = os.environ.get("COPNET_DATA_DIR", "").strip()
    if base:
        return Path(base).expanduser() / "media"
    return Path.home() / ".copenet" / "media"


def default_chat_attachments_dir() -> Path:
    """Return default chat-attachment root: COPNET_DATA_DIR/attachments or ~/.copenet/attachments.

    Stores image (and future file) bytes uploaded into the chat composer, keyed by
    attachment id, separate from the media library (which is its own ingestion lane).
    """
    base = os.environ.get("COPNET_DATA_DIR", "").strip()
    if base:
        return Path(base).expanduser() / "attachments"
    return Path.home() / ".copenet" / "attachments"


def default_session_state_dir() -> Path:
    """Return default session state root under the sessions data tree."""
    return default_sessions_dir() / "state"


def default_artifacts_dir() -> Path:
    """Return default runtime artifact root under the sessions data tree."""
    return default_sessions_dir() / "artifacts"


def default_edit_backups_dir() -> Path:
    """Return default edit-backup root (pre-edit file content for revert)."""
    return default_sessions_dir() / "edit-backups"


def default_provider_auth_dir() -> Path:
    """Return default provider auth root: COPNET_DATA_DIR/providers/auth or ~/.copenet/providers/auth."""
    base = os.environ.get("COPNET_DATA_DIR", "").strip()
    if base:
        return Path(base).expanduser() / "providers" / "auth"
    return Path.home() / ".copenet" / "providers" / "auth"


def default_personas_dir() -> Path:
    """Return default Persona Home root: COPNET_DATA_DIR/personas or ~/.copenet/personas."""
    base = os.environ.get("COPNET_DATA_DIR", "").strip()
    if base:
        return Path(base).expanduser() / "personas"
    return Path.home() / ".copenet" / "personas"


def default_workspace_intel_path() -> Path:
    """Return default workspace intelligence cache path."""
    base = os.environ.get("COPNET_DATA_DIR", "").strip()
    if base:
        return Path(base).expanduser() / "workspace-intel.json"
    return Path.home() / ".copenet" / "workspace-intel.json"


def default_movies_dir() -> Path:
    """Return Movie Lab root: COPNET_DATA_DIR/movies or ~/.copenet/movies."""
    base = os.environ.get("COPNET_DATA_DIR", "").strip()
    if base:
        return Path(base).expanduser() / "movies"
    return Path.home() / ".copenet" / "movies"
