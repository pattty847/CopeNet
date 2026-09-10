"""Run optional title, memory and briefing work after terminal persistence."""

from __future__ import annotations


from copenet.core._config import (
    auto_memory_extraction_enabled,
)
from copenet.core.runtime import RunRecord

from .run_types import RunAdmission


async def notify_after_run(
    orchestrator, admission: RunAdmission, run_record: RunRecord, assistant_text: str, emit_event
):
    if run_record.output_summary and admission.is_first_turn and not (admission.entry.title or "").strip():
        try:
            orchestrator._schedule_title_generation(
                session_key=admission.session_key,
                provider_name=admission.provider_name,
                model=run_record.model,
                first_user_message=admission.message,
                first_assistant_message=assistant_text,
            )
        except Exception as exc:
            admission.trace.record("post_run_side_effect_failed", {"stage": "title", "error": str(exc)})
    memory_created = []
    if auto_memory_extraction_enabled():
        try:
            memory_changes = orchestrator._memory_service.extract_from_run(
                user_message=admission.message, run_record=run_record
            )
            memory_created = list(memory_changes.created)
        except Exception as exc:
            admission.trace.record("post_run_side_effect_failed", {"stage": "memory", "error": str(exc)})
    else:
        admission.trace.record(
            "post_run_side_effect_skipped", {"stage": "memory", "reason": "auto_extraction_disabled"}
        )
    if memory_created:
        admission.trace.record(
            "memory_extracted",
            {
                "count": len(memory_created),
                "itemIds": [item.id for item in memory_created],
                "categories": [item.category for item in memory_created],
            },
        )
    if emit_event is not None and memory_created:
        try:
            for item in memory_created:
                await emit_event(
                    "memory.changed",
                    {
                        "item": item.to_public_dict(),
                        "reason": "run_extraction",
                        "sessionKey": admission.session_key,
                        "runId": admission.run_id,
                    },
                )
        except Exception as exc:
            admission.trace.record("post_run_side_effect_failed", {"stage": "memory_emit", "error": str(exc)})
    try:
        briefing_payload = orchestrator.get_return_briefing()
        if emit_event is not None and briefing_payload is not None:
            await emit_event("briefing.ready", {"briefing": briefing_payload})
    except Exception as exc:
        admission.trace.record("post_run_side_effect_failed", {"stage": "briefing", "error": str(exc)})
