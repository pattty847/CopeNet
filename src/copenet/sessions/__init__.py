"""Compatibility shim — implementation moved to copenet.core.sessions."""
from copenet.core.sessions import (  # noqa: F401
    SessionIndexEntry,
    SessionStore,
    TranscriptMessage,
    TranscriptStore,
)

__all__ = ["SessionIndexEntry", "SessionStore", "TranscriptMessage", "TranscriptStore"]
