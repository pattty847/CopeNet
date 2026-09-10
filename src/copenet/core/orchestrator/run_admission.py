"""Validate a send and reserve its session under the orchestrator lock."""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from . import Orchestrator
    from .requests import ChatSendRequest

import asyncio
from pathlib import Path
from uuid import uuid4

from copenet.core.harness.responses_items import image_content_part
from copenet.core.orchestrator.market_context import (
    resolve_market_context,
    admit_chart_turn,
    update_chart_admission,
    chart_retry_status,
    chart_reference_with_trust,
)
from copenet.core.sessions.transcript_store import utc_now_iso as transcript_now
from copenet.core.tracing import RunTraceWriter

from .run_types import RunAdmission


async def admit_run(orchestrator: "Orchestrator", request: "ChatSendRequest"):
    session_key = request.session_key.strip()
    message = request.message.strip()
    if not session_key:
        raise ValueError("session_key is required")
    attachment_store = orchestrator._chat_attachment_store
    current_image_parts: list[dict] = []
    attachment_refs: list[dict] = []
    for attachment_id in request.attachment_ids:
        attachment = attachment_store.get(attachment_id)
        if attachment is None:
            continue
        data_url = attachment_store.data_url(attachment_id)
        if not data_url:
            continue
        current_image_parts.append(image_content_part(data_url))
        attachment_refs.append(attachment.to_transcript_ref())
    if not message and (not current_image_parts):
        raise ValueError("message is required")
    idempotency_key = request.idempotency_key.strip() if request.idempotency_key else ""
    run_id = idempotency_key or str(uuid4())
    provider_name = request.provider.strip() or "openai-codex"
    if provider_name not in orchestrator._providers:
        init_error = orchestrator._provider_init_errors.get(provider_name)
        if init_error:
            raise RuntimeError(f"provider unavailable: {provider_name} ({init_error})")
        raise ValueError(f"unsupported provider: {provider_name}")
    market_context = resolve_market_context(orchestrator, request, run_id)
    market_reference = chart_reference_with_trust(orchestrator, market_context)
    market_metadata = {"marketContext": market_reference} if market_reference else {}
    dedupe_key = f"chat:{session_key}:{idempotency_key}" if idempotency_key else None
    prior_history = orchestrator.history(session_key=session_key, limit=2)
    is_first_turn = len(prior_history) == 0
    run_started_at = transcript_now()
    trace_settings = orchestrator._observability_store.load_settings()
    trace = RunTraceWriter(
        run_id=run_id,
        session_key=session_key,
        provider=provider_name,
        model=request.model,
        enabled=True,
        debug=trace_settings.debug_capture,
        root_dir=orchestrator._observability_store.trace_root,
    )
    async with orchestrator._lock:
        if market_context is not None:
            active_run = orchestrator._active_run_by_session.get(session_key)
            if active_run and active_run != run_id:
                from . import SessionInFlightError

                raise SessionInFlightError(active_run)
            admission = admit_chart_turn(orchestrator, request, market_context)
            if not admission["new"]:
                status = chart_retry_status(orchestrator, request, admission, active_run)
                return {"runId": admission["runId"], "status": status}
        if dedupe_key is not None:
            cached = orchestrator._idempotency_cache.get(dedupe_key)
            if cached is not None:
                return {"runId": run_id, "status": "cached", "cached": True, "result": cached}
        active_run = orchestrator._active_run_by_session.get(session_key)
        if active_run:
            if active_run == run_id:
                return {"runId": run_id, "status": "in_flight"}
            from . import SessionInFlightError

            raise SessionInFlightError(active_run)
        try:
            persona_context = orchestrator._persona_service.build_prompt_context(
                provider=provider_name,
                model=request.model,
                privacy_tier=request.persona_privacy_tier,
                query=message,
            )
            resolved_persona_id = request.persona_id or persona_context.persona_id
            resolved_persona_flavor_id = request.persona_flavor_id or persona_context.flavor_id
            resolved_persona_privacy_tier = request.persona_privacy_tier or persona_context.privacy_tier
            entry = orchestrator._session_store.resolve_or_create(
                session_key=session_key,
                provider=provider_name,
                model=request.model,
                system_prompt_id=request.system_prompt_id,
                task_prompt_id=request.task_prompt_id,
                persona_id=resolved_persona_id,
                persona_flavor_id=resolved_persona_flavor_id,
                persona_privacy_tier=resolved_persona_privacy_tier,
                workspace_root=orchestrator.validate_workspace_root(request.workspace_root)
                if request.workspace_root
                else None,
            )
            entry = orchestrator._session_store.assert_session_binding(
                session_key=session_key,
                provider=provider_name,
                model=request.model,
                system_prompt_id=request.system_prompt_id,
                task_prompt_id=request.task_prompt_id,
                persona_id=resolved_persona_id,
                persona_flavor_id=resolved_persona_flavor_id,
                persona_privacy_tier=resolved_persona_privacy_tier,
                workspace_root=entry.workspace_root or request.workspace_root,
            )
            session_workspace_root = (
                Path(orchestrator.validate_workspace_root(entry.workspace_root))
                if entry.workspace_root
                else orchestrator._workdir
            )
            orchestrator._session_store.mark_run_started(session_key=session_key, run_id=run_id)
        except Exception:
            update_chart_admission(orchestrator, request, "failed")
            raise
        abort_event = asyncio.Event()
        orchestrator._active_abort_by_run[run_id] = abort_event
        orchestrator._active_run_by_session[session_key] = run_id
    return RunAdmission(
        request=request,
        session_key=session_key,
        message=message,
        run_id=run_id,
        provider_name=provider_name,
        entry=entry,
        session_workspace_root=session_workspace_root,
        abort_event=abort_event,
        trace=trace,
        market_context=market_context,
        market_reference=market_reference,
        market_metadata=market_metadata,
        dedupe_key=dedupe_key,
        run_started_at=run_started_at,
        is_first_turn=is_first_turn,
        attachment_refs=attachment_refs,
        current_image_parts=current_image_parts,
    )
