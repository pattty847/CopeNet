"""Compatibility shim — implementation moved to copenet.core.tracing."""
from copenet.core.tracing import RunTraceWriter, utc_now_iso  # noqa: F401

__all__ = ["RunTraceWriter", "utc_now_iso"]
