"""Coordinate one admitted chat turn through explicit lifecycle stages."""

from __future__ import annotations
import asyncio
from typing import TYPE_CHECKING
from .requests import ChatSendRequest, ChatEmit, SideEventEmit
from .run_admission import admit_run
from .run_delivery import RunDelivery
from .run_types import RunEvents, RunInput
from .run_input import prepare_run_input
from .run_harness import start_harness
from .run_events import consume_event
from .run_finalization import finish_success, finish_failure
from .run_notifications import notify_after_run

if TYPE_CHECKING:
    from . import Orchestrator


async def send_chat(
    orchestrator: Orchestrator,
    request: ChatSendRequest,
    emit: ChatEmit,
    *,
    emit_event: SideEventEmit | None = None,
) -> dict:
    """Admit once, persist one outcome, and release only this run's session lock."""
    admission = await admit_run(orchestrator, request)
    if isinstance(admission, dict):
        return admission
    events = RunEvents()
    prepared: RunInput | None = None
    delivery = RunDelivery(emit, emit_event, admission.trace)
    side_emit = delivery.emit_event if emit_event is not None else None
    try:
        if admission.market_context is not None and side_emit is not None:
            await side_emit(
                "chat.admitted",
                {"runId": admission.run_id, "status": "started", "sessionKey": admission.session_key},
            )
        admission.trace.record(
            "run_started",
            {
                **admission.market_metadata,
                "messageChars": len(admission.message),
                "attachmentCount": len(admission.attachment_refs),
                "requestedToolIds": list(request.requested_tool_ids),
                "profile": request.system_prompt_id,
                "taskMode": request.task_prompt_id,
                "workdir": str(admission.session_workspace_root),
            },
        )
        admission.trace.record_debug("run_input", {"messagePreview": admission.message[:2000]})
        admission.trace.record(
            "session_resolved",
            {
                "providerSessionId": admission.entry.provider_session_id,
                "sessionId": admission.entry.session_id,
            },
        )
        prepared = await prepare_run_input(orchestrator, admission)
        plan, event_stream = await start_harness(orchestrator, admission, prepared, events, side_emit)
        if not plan.will_attempt_tool_loop:
            admission.trace.record(
                "provider_turn_started",
                {"phase": "provider", "providerSessionId": admission.entry.provider_session_id},
            )
        try:
            async for event in event_stream:
                await consume_event(orchestrator, admission, prepared, events, event, delivery.emit)
                if event.kind == "final":
                    break
        finally:
            await event_stream.aclose()
        if admission.abort_event.is_set():
            payload = finish_failure(
                orchestrator, admission, prepared, events, RuntimeError("Run interrupted"), interrupted=True
            )
            await delivery.emit(payload)
            return {"runId": admission.run_id, "status": "interrupted"}
        if not plan.will_attempt_tool_loop:
            admission.trace.record(
                "provider_turn_completed",
                {
                    "phase": "provider",
                    "providerSessionId": admission.entry.provider_session_id,
                    "deltaCount": len(events.assistant_parts),
                },
            )
        record, payload = finish_success(orchestrator, admission, prepared, events)
        await delivery.emit(payload)
        await notify_after_run(
            orchestrator, admission, record, "".join(events.assistant_parts).strip(), side_emit
        )
        return {"runId": admission.run_id, "status": "ok"}
    except asyncio.CancelledError as exc:
        admission.abort_event.set()
        if not events.terminal_persisted:
            finish_failure(orchestrator, admission, prepared, events, exc, interrupted=True)
        raise
    except Exception as exc:
        # A persistence/admission failure after the terminal append must remain
        # visible, but must never append a second terminal execution outcome.
        if events.terminal_persisted:
            raise
        payload = finish_failure(orchestrator, admission, prepared, events, exc)
        await delivery.emit(payload)
        return {"runId": admission.run_id, "status": "error", "summary": str(exc)}
    finally:
        async with orchestrator._lock:
            orchestrator._active_abort_by_run.pop(admission.run_id, None)
            if orchestrator._active_run_by_session.get(admission.session_key) == admission.run_id:
                orchestrator._active_run_by_session.pop(admission.session_key, None)
            orchestrator._session_store.mark_run_finished(
                session_key=admission.session_key, run_id=admission.run_id
            )
