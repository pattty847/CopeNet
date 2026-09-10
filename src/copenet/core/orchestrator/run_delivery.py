"""Best-effort event delivery without changing execution outcome."""

from __future__ import annotations
from .requests import ChatEmit, SideEventEmit
from copenet.core.tracing import RunTraceWriter


class RunDelivery:
    def __init__(self, emit: ChatEmit, emit_event: SideEventEmit | None, trace: RunTraceWriter):
        self._emit = emit
        self._emit_event = emit_event
        self._trace = trace

    async def emit(self, payload: dict) -> None:
        try:
            await self._emit(payload)
        except Exception as exc:
            self._trace.record("event_delivery_failed", {"state": payload.get("state"), "error": str(exc)})

    async def emit_event(self, name: str, payload: dict) -> None:
        if self._emit_event is None:
            return
        try:
            await self._emit_event(name, payload)
        except Exception as exc:
            self._trace.record("event_delivery_failed", {"event": name, "error": str(exc)})
