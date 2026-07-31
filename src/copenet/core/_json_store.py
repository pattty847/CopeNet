"""Small JSON file helpers for CopeNet's local stores."""

from __future__ import annotations

import json
import os
from pathlib import Path
import threading
from typing import Any


class JsonStoreError(RuntimeError):
    """Raised when a JSON store file exists but cannot be read or parsed.

    Distinct from "file missing", which is the benign not-created-yet case.
    Callers must not treat this the same as an empty store — doing so lets a
    later save silently overwrite recoverable data with just the new item.
    """


_PATH_LOCKS_GUARD = threading.Lock()
_PATH_LOCKS: dict[str, threading.RLock] = {}


def _path_lock(path: Path) -> threading.RLock:
    """Return the process-local lock shared by every store instance for path."""
    key = str(path.resolve(strict=False))
    with _PATH_LOCKS_GUARD:
        lock = _PATH_LOCKS.get(key)
        if lock is None:
            lock = threading.RLock()
            _PATH_LOCKS[key] = lock
        return lock


def read_json(path: Path, fallback: Any) -> Any:
    """Read JSON from ``path``.

    A missing or blank file is the benign "nothing saved yet" case and
    returns ``fallback``. A file that exists but is unreadable or corrupt is
    NOT the same as empty — it still holds recoverable data — so that case is
    quarantined (a ``.corrupt`` copy is written alongside it) and raised as
    ``JsonStoreError`` instead of being silently swallowed into ``fallback``.
    """
    with _path_lock(path):
        if not path.exists():
            return fallback
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise JsonStoreError(f"could not read {path}: {exc}") from exc
        if not text.strip():
            return fallback
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            backup = path.with_suffix(path.suffix + ".corrupt")
            try:
                backup.write_text(text, encoding="utf-8")
            except OSError:
                backup = None  # best-effort; still fail loud below
            raise JsonStoreError(
                f"{path} is corrupt and was not parseable"
                + (f"; corrupt copy saved to {backup}" if backup else "")
            ) from exc


def write_json_atomic(path: Path, payload: Any, *, trailing_newline: bool = True) -> None:
    with _path_lock(path):
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        body = json.dumps(payload, ensure_ascii=False, indent=2)
        if trailing_newline:
            body += "\n"
        tmp.write_text(body, encoding="utf-8")
        tmp.replace(path)


def write_text_atomic(path: Path, body: str) -> None:
    """Atomically write text via temp-file + rename (honors the atomic-write invariant)."""
    with _path_lock(path):
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(body, encoding="utf-8")
        tmp.replace(path)


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    with _path_lock(path):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
