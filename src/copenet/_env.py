"""Dependency-free `.env` loader.

CopeNet reads all secrets from ``os.environ`` but is launched via ``uv run copenet``,
which does not auto-load a project ``.env``. This loads simple ``KEY=VALUE`` pairs from
the nearest ``.env`` without overriding values already present in the environment.
"""

from __future__ import annotations

import os
from pathlib import Path


def _find_env_files() -> list[Path]:
    """Locate `.env` plus optional ignored `.env.local` for feature credentials."""
    root: Path | None = None
    for directory in (Path.cwd(), *Path.cwd().parents):
        candidate = directory / ".env"
        if candidate.is_file():
            root = directory
            break
    if root is None:
        # Editable/source layout: this file lives at <repo>/src/copenet/_env.py
        repo_root = Path(__file__).resolve().parents[2]
        if (repo_root / ".env").is_file():
            root = repo_root
    if root is None:
        return []
    return [path for path in (root / ".env", root / ".env.local") if path.is_file()]


def load_project_env() -> None:
    """Populate `os.environ` from the project `.env` for keys not already set."""
    for env_path in _find_env_files():
        try:
            lines = env_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, _, value = stripped.partition("=")
            key = key.strip()
            if not key or key in os.environ:
                continue
            os.environ[key] = value.strip().strip('"').strip("'")
