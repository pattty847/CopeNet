"""Operator-managed permission state (the global shell allowlist)."""

from .store import PermissionStore, normalize_command

__all__ = ["PermissionStore", "normalize_command"]
