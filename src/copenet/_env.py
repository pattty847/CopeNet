"""Dependency-free `.env` loader.

CopeNet reads all secrets from ``os.environ`` but is launched via ``uv run copenet``,
which does not auto-load a project ``.env``. This loads simple ``KEY=VALUE`` pairs from
the nearest ``.env`` without overriding values already present in the environment.
"""

from __future__ import annotations

import os
from pathlib import Path


def _find_env_file() -> Path | None:
    """Locate a `.env`: walk up from cwd, then fall back to the repo root."""
    for directory in (Path.cwd(), *Path.cwd().parents):
        candidate = directory / ".env"
        if candidate.is_file():
            return candidate
    # Editable/source layout: this file lives at <repo>/src/copenet/_env.py
    repo_root_candidate = Path(__file__).resolve().parents[2] / ".env"
    if repo_root_candidate.is_file():
        return repo_root_candidate
    return None


def load_project_env() -> None:
    """Populate `os.environ` from the project `.env` for keys not already set."""
    env_path = _find_env_file()
    if env_path is None:
        return
    try:
        lines = env_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        key = key.strip()
        if not key or key in os.environ:
            continue
        os.environ[key] = value.strip().strip('"').strip("'")
