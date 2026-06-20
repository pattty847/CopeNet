"""Global, operator-managed shell allowlist (Access & Permissions — Brick E).

When an operator picks "Always allow" on an approval prompt, the exact command is
persisted here. The shell handler consults this list as a standing approval: a
listed command runs with full shell in any Access mode, without asking again.

Scope is global per data dir (one entry list under ~/.copenet or COPNET_DATA_DIR),
matching the "global over per-session" decision. Commands are stored
whitespace-normalized so trivial spacing differences don't create duplicates.
"""

from __future__ import annotations

import json
from pathlib import Path
import threading
from typing import Any

from copenet.core.sessions.session_store import utc_now_iso


def normalize_command(command: Any) -> str:
    """Collapse whitespace so `npm  test` and `npm test` match as one entry."""
    return " ".join(str(command or "").split())


class PermissionStore:
    """In-memory + JSON-persisted set of operator-approved shell commands."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        # {normalized_command: {"command", "addedAt"}}
        self._entries: dict[str, dict[str, str]] = {}
        self._load_unlocked()

    def _load_unlocked(self) -> None:
        if not self._path.exists():
            self._entries = {}
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            self._entries = {}
            return
        rows = raw.get("commands") if isinstance(raw, dict) else None
        entries: dict[str, dict[str, str]] = {}
        if isinstance(rows, list):
            for item in rows:
                command = normalize_command(item.get("command") if isinstance(item, dict) else item)
                if not command:
                    continue
                added_at = ""
                if isinstance(item, dict):
                    added_at = str(item.get("addedAt") or item.get("added_at") or "")
                entries[command] = {"command": command, "addedAt": added_at or utc_now_iso()}
        self._entries = entries

    def _save_unlocked(self) -> None:
        ordered = sorted(self._entries.values(), key=lambda e: e["command"])
        payload = {"commands": ordered}
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp.replace(self._path)

    def is_allowed(self, command: str) -> bool:
        """True when this exact (normalized) command is on the global allowlist."""
        key = normalize_command(command)
        if not key:
            return False
        with self._lock:
            return key in self._entries

    def add(self, command: str) -> dict[str, str] | None:
        """Persist a command to the allowlist. Returns the stored entry (idempotent)."""
        key = normalize_command(command)
        if not key:
            return None
        with self._lock:
            existing = self._entries.get(key)
            if existing is not None:
                return dict(existing)
            entry = {"command": key, "addedAt": utc_now_iso()}
            self._entries[key] = entry
            self._save_unlocked()
            return dict(entry)

    def remove(self, command: str) -> bool:
        """Drop a command from the allowlist. Returns True if it was present."""
        key = normalize_command(command)
        with self._lock:
            if key not in self._entries:
                return False
            del self._entries[key]
            self._save_unlocked()
            return True

    def list_commands(self) -> list[dict[str, str]]:
        """Return all allowlist entries, command-sorted."""
        with self._lock:
            return [dict(entry) for entry in sorted(self._entries.values(), key=lambda e: e["command"])]
