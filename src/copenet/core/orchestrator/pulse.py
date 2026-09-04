"""Pulse creation and save helpers for session-based follow-up opportunities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from copenet.core.model_request import ProviderTextRequest, collect_provider_text
from copenet.core.orchestrator.catalog import create_session_with_profile, session_payload
from copenet.core.orchestrator.merge import merge_sessions
from copenet.core.pulse import PulseRecord
from copenet.core.sessions import TranscriptMessage
from copenet.core.sessions.session_store import utc_now_iso
from copenet.prompts import PromptPurpose, compose_prompt

if TYPE_CHECKING:
    from . import Orchestrator
    from .requests import SideEventEmit


@dataclass(frozen=True)
class PulseSourceContext:
    session_key: str
    title: str
    provider: str
    model: str | None
    workspace_root: str | None
    history: list[dict[str, Any]]
    state: dict[str, Any] | None


async def create_pulse_from_session(
    orchestrator: "Orchestrator",
    *,
    session_key: str,
    provider: str,
    model: str | None,
    system_prompt_id: str | None,
    task_prompt_id: str | None,
    emit_event: SideEventEmit | None = None,
) -> dict[str, Any]:
    context = _load_source_context(orchestrator, session_key)
    title, summary, why_now = await _generate_pulse_copy(
        orchestrator,
        context=context,
        provider_id=provider,
        model=model,
        system_prompt_id=system_prompt_id,
        task_prompt_id=task_prompt_id,
    )
    now = utc_now_iso()
    record = orchestrator._pulse_store.create(
        PulseRecord(
            pulse_id=f"pulse-{uuid4()}",
            status="new",
            title=title,
            summary=summary,
            why_now=why_now,
            source_session_keys=[context.session_key],
            source_run_ids=_source_run_ids(context.history),
            created_at=now,
            updated_at=now,
        )
    )
    payload = _public_pulse(record, orchestrator=orchestrator)
    if emit_event is not None:
        await _emit_pulse_update(emit_event, payload)
    return payload


def list_pulses(orchestrator: "Orchestrator") -> list[dict[str, Any]]:
    records = orchestrator._pulse_store.list(status="new")
    return [_public_pulse(record, orchestrator=orchestrator) for record in records]


async def dismiss_pulse(
    orchestrator: "Orchestrator",
    *,
    pulse_id: str,
    emit_event: SideEventEmit | None = None,
) -> dict[str, Any]:
    record = orchestrator._pulse_store.get(pulse_id.strip())
    if record is None:
        raise KeyError(f"unknown pulse_id: {pulse_id.strip()}")
    updated = orchestrator._pulse_store.save(
        PulseRecord(
            pulse_id=record.pulse_id,
            status="dismissed",
            title=record.title,
            summary=record.summary,
            why_now=record.why_now,
            source_session_keys=list(record.source_session_keys),
            source_run_ids=list(record.source_run_ids),
            created_at=record.created_at,
            updated_at=record.updated_at,
            saved_at=record.saved_at,
            dismissed_at=utc_now_iso(),
        )
    )
    payload = _public_pulse(updated, orchestrator=orchestrator)
    if emit_event is not None:
        await _emit_pulse_update(emit_event, payload)
    return payload


async def save_pulses(
    orchestrator: "Orchestrator",
    *,
    pulse_ids: list[str],
    provider: str,
    model: str | None,
    system_prompt_id: str | None,
    task_prompt_id: str | None,
    workspace_root: str | None,
    emit_event: SideEventEmit | None = None,
) -> dict[str, Any]:
    selected = _load_selected_pulses(orchestrator, pulse_ids)
    if len(selected) == 1:
        pulse = selected[0]
        result = _save_single_pulse(
            orchestrator,
            pulse=pulse,
            provider=provider,
            model=model,
            system_prompt_id=system_prompt_id,
            task_prompt_id=task_prompt_id,
            workspace_root=workspace_root,
        )
    else:
        result = await _save_pulse_workspace(
            orchestrator,
            pulses=selected,
            provider=provider,
            model=model,
            system_prompt_id=system_prompt_id,
            task_prompt_id=task_prompt_id,
            workspace_root=workspace_root,
            emit_event=emit_event,
        )
    for pulse in selected:
        saved = orchestrator._pulse_store.save(
            PulseRecord(
                pulse_id=pulse.pulse_id,
                status="saved",
                title=pulse.title,
                summary=pulse.summary,
                why_now=pulse.why_now,
                source_session_keys=list(pulse.source_session_keys),
                source_run_ids=list(pulse.source_run_ids),
                created_at=pulse.created_at,
                updated_at=pulse.updated_at,
                saved_at=utc_now_iso(),
                dismissed_at=pulse.dismissed_at,
            )
        )
        if emit_event is not None:
            await _emit_pulse_update(emit_event, _public_pulse(saved, orchestrator=orchestrator))
    return result


async def _save_pulse_workspace(
    orchestrator: "Orchestrator",
    *,
    pulses: list[PulseRecord],
    provider: str,
    model: str | None,
    system_prompt_id: str | None,
    task_prompt_id: str | None,
    workspace_root: str | None,
    emit_event: SideEventEmit | None,
) -> dict[str, Any]:
    source_session_keys = _dedupe([key for pulse in pulses for key in pulse.source_session_keys])
    created = await merge_sessions(
        orchestrator,
        source_session_keys=source_session_keys,
        provider=provider,
        model=model,
        system_prompt_id=system_prompt_id,
        task_prompt_id=task_prompt_id,
        workspace_root=workspace_root,
        title=f"Pulse Workspace — {len(pulses)} Saved Pulses",
        emit_event=emit_event,
    )
    state_record = orchestrator._session_state_store.get_or_create(created["session"]["key"])
    state_record.pulse_state = {
        "status": "saved",
        "source_pulse_ids": [pulse.pulse_id for pulse in pulses],
        "source_session_keys": source_session_keys,
        "saved_at": utc_now_iso(),
        "mode": "merge",
    }
    orchestrator._session_state_store.save(state_record)
    return created


def _save_single_pulse(
    orchestrator: "Orchestrator",
    *,
    pulse: PulseRecord,
    provider: str,
    model: str | None,
    system_prompt_id: str | None,
    task_prompt_id: str | None,
    workspace_root: str | None,
) -> dict[str, Any]:
    source_key = pulse.source_session_keys[0]
    source_entry = orchestrator._session_store.get(source_key)
    title_suffix = source_entry.title if source_entry and source_entry.title else source_key
    resolved_workspace_root = orchestrator.validate_workspace_root(workspace_root) if workspace_root else None
    created_session = create_session_with_profile(
        orchestrator,
        provider=provider,
        model=model,
        title=f"Pulse — {title_suffix}",
        system_prompt_id=system_prompt_id,
        task_prompt_id=task_prompt_id,
        workspace_root=resolved_workspace_root,
    )
    run_id = f"pulse-{uuid4()}"
    content = _build_single_pulse_brief(orchestrator, pulse)
    orchestrator._transcript_store.append_message(
        str(created_session["sessionId"]),
        TranscriptMessage(
            run_id=run_id,
            role="assistant",
            content=content,
            provider=provider,
            model=model,
            provider_session_id=None,
            timestamp=utc_now_iso(),
            state="final",
        ),
    )
    state_record = orchestrator._session_state_store.get_or_create(created_session["key"])
    state_record.task_summary = pulse.summary
    state_record.pulse_state = {
        "status": "saved",
        "source_pulse_ids": [pulse.pulse_id],
        "source_session_keys": list(pulse.source_session_keys),
        "saved_at": utc_now_iso(),
        "mode": "single",
        "title": pulse.title,
        "why_now": pulse.why_now,
    }
    orchestrator._session_state_store.save(state_record)
    return {"session": created_session, "mergeState": None}


def _build_single_pulse_brief(orchestrator: "Orchestrator", pulse: PulseRecord) -> str:
    session_titles: list[str] = []
    for session_key in pulse.source_session_keys:
        entry = orchestrator._session_store.get(session_key)
        session_titles.append(entry.title or session_key if entry is not None else session_key)
    lines = [
        f"Pulse saved from {len(pulse.source_session_keys)} source session{'s' if len(pulse.source_session_keys) != 1 else ''}.",
        "",
        f"## {pulse.title}",
        pulse.summary,
        "",
        f"Why now: {pulse.why_now}",
        "",
        "Source sessions:",
    ]
    lines.extend(f"- {title} (`{key}`)" for title, key in zip(session_titles, pulse.source_session_keys, strict=False))
    return "\n".join(lines).strip()


def _load_selected_pulses(orchestrator: "Orchestrator", pulse_ids: list[str]) -> list[PulseRecord]:
    rows: list[PulseRecord] = []
    seen: set[str] = set()
    for pulse_id in pulse_ids:
        key = str(pulse_id or "").strip()
        if not key or key in seen:
            continue
        seen.add(key)
        record = orchestrator._pulse_store.get(key)
        if record is None:
            raise KeyError(f"unknown pulse_id: {key}")
        if record.status == "dismissed":
            raise RuntimeError(f"pulse is not active: {key}")
        rows.append(record)
    if not rows:
        raise ValueError("at least one pulse is required")
    return rows


def _load_source_context(orchestrator: "Orchestrator", session_key: str) -> PulseSourceContext:
    entry = orchestrator._session_store.get(session_key.strip())
    if entry is None:
        raise KeyError(f"unknown session_key: {session_key}")
    if entry.archived:
        raise RuntimeError(f"session is archived: {session_key}")
    return PulseSourceContext(
        session_key=entry.session_key,
        title=entry.title or entry.session_key,
        provider=entry.provider,
        model=entry.model,
        workspace_root=entry.workspace_root,
        history=orchestrator.history(entry.session_key, limit=1000),
        state=orchestrator.resolve_session_state(entry.session_key),
    )


async def _generate_pulse_copy(
    orchestrator: "Orchestrator",
    *,
    context: PulseSourceContext,
    provider_id: str,
    model: str | None,
    system_prompt_id: str | None,
    task_prompt_id: str | None,
) -> tuple[str, str, str]:
    provider = orchestrator._providers.get(provider_id)
    if provider is None:
        raise ValueError(f"unsupported provider: {provider_id}")
    prompt = _build_pulse_prompt(context)
    text = await collect_provider_text(
        provider=provider,
        request=ProviderTextRequest(
            purpose=PromptPurpose.SPECIALIZED,
            phase="pulse_generation",
            prompt=prompt,
            model=model,
            system_prompt=compose_prompt(system_prompt_id, task_prompt_id),
        ),
    )
    if not text:
        raise RuntimeError(f"pulse generation returned no text for {context.session_key}")
    parsed = _parse_pulse_copy(text)
    if parsed is not None:
        return parsed
    return (
        context.title,
        text.splitlines()[0].strip()[:160] or f"Follow up on {context.title}",
        "This thread looks worth revisiting.",
    )


def _build_pulse_prompt(context: PulseSourceContext) -> str:
    recent_transcript: list[str] = []
    for message in context.history[-8:]:
        role = str(message.get("role") or "assistant")
        content = str(message.get("content") or "").strip()
        if content:
            recent_transcript.append(f"{role}: {content}")
    state = context.state or {}
    return "\n".join(
        [
            "Create a CopeNet Pulse from this session.",
            "Return exactly three labeled lines:",
            "Title: ...",
            "Summary: ...",
            "Why now: ...",
            f"Source session key: {context.session_key}",
            f"Source title: {context.title}",
            f"Task summary: {str(state.get('task_summary') or '').strip() or 'None'}",
            f"Prior decisions: {', '.join(_string_list(state.get('prior_decisions'))) or 'None'}",
            f"Open questions: {', '.join(_string_list(state.get('unresolved_questions'))) or 'None'}",
            "Recent transcript:",
            "\n".join(recent_transcript) or "None",
        ]
    )


def _parse_pulse_copy(text: str) -> tuple[str, str, str] | None:
    title = ""
    summary = ""
    why_now = ""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("title:"):
            title = stripped.split(":", 1)[1].strip()
        elif stripped.lower().startswith("summary:"):
            summary = stripped.split(":", 1)[1].strip()
        elif stripped.lower().startswith("why now:"):
            why_now = stripped.split(":", 1)[1].strip()
    if title and summary and why_now:
        return title, summary, why_now
    return None


def _public_pulse(record: PulseRecord, *, orchestrator: "Orchestrator") -> dict[str, Any]:
    source_sessions: list[dict[str, str]] = []
    for session_key in record.source_session_keys:
        entry = orchestrator._session_store.get(session_key)
        source_sessions.append(
            {
                "sessionKey": session_key,
                "title": entry.title or session_key if entry is not None else session_key,
            }
        )
    return {
        "pulseId": record.pulse_id,
        "status": record.status,
        "title": record.title,
        "summary": record.summary,
        "whyNow": record.why_now,
        "sourceSessionKeys": list(record.source_session_keys),
        "sourceRunIds": list(record.source_run_ids),
        "sourceSessions": source_sessions,
        "createdAt": record.created_at,
        "updatedAt": record.updated_at,
        "savedAt": record.saved_at,
        "dismissedAt": record.dismissed_at,
    }


async def _emit_pulse_update(emit_event: SideEventEmit, pulse: dict[str, Any]) -> None:
    try:
        await emit_event("pulse.updated", {"pulse": pulse})
    except Exception:
        return


def _source_run_ids(history: list[dict[str, Any]]) -> list[str]:
    rows: list[str] = []
    seen: set[str] = set()
    for message in reversed(history):
        run_id = str(message.get("runId") or "").strip()
        if run_id and run_id not in seen:
            seen.add(run_id)
            rows.append(run_id)
        if len(rows) >= 3:
            break
    return rows


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    rows: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text:
            rows.append(text)
    return rows


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    rows: list[str] = []
    for value in values:
        key = str(value or "").strip()
        if not key or key in seen:
            continue
        seen.add(key)
        rows.append(key)
    return rows
