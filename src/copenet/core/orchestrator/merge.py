"""Session merge helpers for building a new merged Agent session."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from copenet.core.orchestrator.catalog import create_session_with_profile, session_payload
from copenet.core.sessions import TranscriptMessage
from copenet.core.sessions.session_store import utc_now_iso
from copenet.prompts import compose_prompt
from copenet.providers import ProviderEvent

if TYPE_CHECKING:
    from . import Orchestrator, SideEventEmit


@dataclass(frozen=True)
class MergeSourceContext:
    session_key: str
    title: str
    provider: str
    model: str | None
    workspace_root: str | None
    history: list[dict[str, Any]]
    state: dict[str, Any] | None
    artifacts: list[dict[str, Any]]


def resolve_merge_state(orchestrator: "Orchestrator", session_key: str) -> dict[str, Any] | None:
    record = orchestrator._session_state_store.get(session_key.strip())
    if record is None or not record.merge_state:
        return None
    return _public_merge_state(record.merge_state)


async def merge_sessions(
    orchestrator: "Orchestrator",
    *,
    source_session_keys: list[str],
    provider: str,
    model: str | None,
    system_prompt_id: str | None,
    task_prompt_id: str | None,
    workspace_root: str | None,
    title: str | None = None,
    emit_event: SideEventEmit | None = None,
) -> dict[str, Any]:
    normalized_sources = _normalize_source_keys(source_session_keys)
    if len(normalized_sources) < 2:
        raise ValueError("at least 2 source sessions are required")

    source_contexts = [_load_source_context(orchestrator, key) for key in normalized_sources]
    resolved_workspace_root = orchestrator.validate_workspace_root(workspace_root) if workspace_root else None
    created_session = create_session_with_profile(
        orchestrator,
        provider=provider,
        model=model,
        title=title or f"Merged Workspace — {len(source_contexts)} Sessions",
        system_prompt_id=system_prompt_id,
        task_prompt_id=task_prompt_id,
        workspace_root=resolved_workspace_root,
    )
    session_key = str(created_session["key"])
    state_record = orchestrator._session_state_store.get_or_create(session_key)
    state_record.task_summary = f"Merged workspace from {len(source_contexts)} sessions."
    state_record.merge_state = _initial_merge_state(source_contexts)
    orchestrator._session_state_store.save(state_record)

    if emit_event is not None:
        await _emit_merge_update(emit_event, session_key, state_record.merge_state)

    async def hydrate() -> None:
        await _hydrate_merge_session(
            orchestrator,
            target_session=session_payload(orchestrator._session_store.get(session_key)),
            source_contexts=source_contexts,
            system_prompt_id=system_prompt_id,
            task_prompt_id=task_prompt_id,
            emit_event=emit_event,
        )

    task = asyncio.create_task(hydrate())
    orchestrator._background_tasks.add(task)
    task.add_done_callback(orchestrator._background_tasks.discard)

    return {
        "session": created_session,
        "mergeState": _public_merge_state(state_record.merge_state),
    }


def _normalize_source_keys(source_session_keys: list[str]) -> list[str]:
    rows: list[str] = []
    seen: set[str] = set()
    for value in source_session_keys:
        key = str(value or "").strip()
        if not key or key in seen:
            continue
        seen.add(key)
        rows.append(key)
    return rows


def _load_source_context(orchestrator: "Orchestrator", session_key: str) -> MergeSourceContext:
    entry = orchestrator._session_store.get(session_key)
    if entry is None:
        raise KeyError(f"unknown session_key: {session_key}")
    if entry.archived:
        raise RuntimeError(f"session is archived: {session_key}")
    title = entry.title or entry.session_key
    return MergeSourceContext(
        session_key=entry.session_key,
        title=title,
        provider=entry.provider,
        model=entry.model,
        workspace_root=entry.workspace_root,
        history=orchestrator.history(entry.session_key, limit=1000),
        state=orchestrator.resolve_session_state(entry.session_key),
        artifacts=orchestrator.list_session_artifacts(entry.session_key, limit=25),
    )


def _initial_merge_state(source_contexts: list[MergeSourceContext]) -> dict[str, Any]:
    return {
        "status": "pending",
        "source_session_keys": [context.session_key for context in source_contexts],
        "total_sources": len(source_contexts),
        "completed_sources": 0,
        "started_at": utc_now_iso(),
        "completed_at": None,
        "brief_run_id": None,
        "brief_artifact_id": None,
        "conflicts": [],
        "sources": [
            {
                "session_key": context.session_key,
                "title": context.title,
                "status": "pending",
                "summary": None,
                "error": None,
                "decision_count": len(_string_list((context.state or {}).get("prior_decisions"))),
                "open_question_count": len(_string_list((context.state or {}).get("unresolved_questions"))),
            }
            for context in source_contexts
        ],
    }


async def _hydrate_merge_session(
    orchestrator: "Orchestrator",
    *,
    target_session: dict[str, Any],
    source_contexts: list[MergeSourceContext],
    system_prompt_id: str | None,
    task_prompt_id: str | None,
    emit_event: SideEventEmit | None,
) -> None:
    session_key = str(target_session["key"])
    record = orchestrator._session_state_store.get_or_create(session_key)
    merge_state = dict(record.merge_state)
    merge_state["status"] = "running"
    record.merge_state = merge_state
    orchestrator._session_state_store.save(record)
    if emit_event is not None:
        await _emit_merge_update(emit_event, session_key, merge_state)

    for index, context in enumerate(source_contexts):
        merge_state = _mark_source_status(merge_state, index, "running")
        record.merge_state = merge_state
        orchestrator._session_state_store.save(record)
        if emit_event is not None:
            await _emit_merge_update(emit_event, session_key, merge_state)
        try:
            summary = await _generate_source_summary(
                orchestrator,
                context=context,
                provider_id=str(target_session["provider"]),
                model=target_session.get("model"),
                system_prompt_id=system_prompt_id,
                task_prompt_id=task_prompt_id,
            )
        except Exception as exc:
            merge_state = _complete_source(merge_state, index, error=str(exc))
        else:
            merge_state = _complete_source(merge_state, index, summary=summary)
        record.merge_state = merge_state
        orchestrator._session_state_store.save(record)
        if emit_event is not None:
            await _emit_merge_update(emit_event, session_key, merge_state)

    conflicts = _detect_conflicts(source_contexts)
    final_status = "complete" if all(source["status"] == "complete" for source in merge_state["sources"]) else "failed"
    merge_state["status"] = final_status
    merge_state["completed_at"] = utc_now_iso()
    merge_state["conflicts"] = conflicts

    brief = _build_merge_brief(source_contexts, merge_state)
    run_id = f"merge-{uuid4()}"
    orchestrator._transcript_store.append_message(
        str(target_session["sessionId"]),
        TranscriptMessage(
            run_id=run_id,
            role="assistant",
            content=brief,
            provider=str(target_session["provider"]),
            model=target_session.get("model"),
            provider_session_id=None,
            timestamp=utc_now_iso(),
            state="final",
        ),
    )
    artifact = orchestrator._artifact_store.create(
        session_key=session_key,
        run_id=run_id,
        artifact_type="merge_brief",
        title="Merged Context Brief",
        body=brief,
        metadata={
            "sourceSessionKeys": [context.session_key for context in source_contexts],
            "conflictCount": len(conflicts),
        },
    )
    record = orchestrator._session_state_store.get_or_create(session_key)
    record.relevant_artifact_ids = [artifact.artifact_id, *[value for value in record.relevant_artifact_ids if value != artifact.artifact_id]]
    merge_state["brief_run_id"] = run_id
    merge_state["brief_artifact_id"] = artifact.artifact_id
    record.merge_state = merge_state
    orchestrator._session_state_store.save(record)
    if emit_event is not None:
        await _emit_merge_update(
            emit_event,
            session_key,
            merge_state,
            message={
                "runId": run_id,
                "role": "assistant",
                "content": brief,
                "provider": str(target_session["provider"]),
                "model": target_session.get("model"),
                "providerSessionId": None,
                "timestamp": utc_now_iso(),
                "state": "final",
            },
        )


async def _generate_source_summary(
    orchestrator: "Orchestrator",
    *,
    context: MergeSourceContext,
    provider_id: str,
    model: str | None,
    system_prompt_id: str | None,
    task_prompt_id: str | None,
) -> str:
    provider = orchestrator._providers.get(provider_id)
    if provider is None:
        raise ValueError(f"unsupported provider: {provider_id}")
    prompt = _build_summary_prompt(context)
    abort_event = asyncio.Event()
    chunks: list[str] = []
    async for event in provider.run(
        prompt,
        provider_session_id=None,
        abort_event=abort_event,
        model=model,
        system_prompt=compose_prompt(system_prompt_id, task_prompt_id),
    ):
        if event.kind == "delta" and event.text:
            chunks.append(event.text)
        if event.kind == "error":
            raise RuntimeError(event.message or "merge summary generation failed")
    summary = "".join(chunks).strip()
    if not summary:
        raise RuntimeError(f"summary generation returned no text for {context.session_key}")
    return summary


def _build_summary_prompt(context: MergeSourceContext) -> str:
    recent_transcript: list[str] = []
    for message in context.history[-8:]:
        role = str(message.get("role") or "assistant")
        content = str(message.get("content") or "").strip()
        if content:
            recent_transcript.append(f"{role}: {content}")
    state = context.state or {}
    artifacts = [str(artifact.get("title") or "").strip() for artifact in context.artifacts if str(artifact.get("title") or "").strip()]
    return "\n".join(
        [
            "Summarize this source session for a merged CopeNet workspace.",
            "Return one concise paragraph plus any key decisions or open questions in plain text.",
            f"Source session key: {context.session_key}",
            f"Source title: {context.title}",
            f"Source provider: {context.provider}",
            f"Source model: {context.model or 'default'}",
            f"Source workspace root: {context.workspace_root or 'default'}",
            f"Task summary: {str(state.get('task_summary') or '').strip() or 'None'}",
            f"Prior decisions: {', '.join(_string_list(state.get('prior_decisions'))) or 'None'}",
            f"Open questions: {', '.join(_string_list(state.get('unresolved_questions'))) or 'None'}",
            f"Artifacts: {', '.join(artifacts[:6]) or 'None'}",
            "Recent transcript:",
            "\n".join(recent_transcript) or "None",
        ]
    )


def _mark_source_status(merge_state: dict[str, Any], index: int, status: str) -> dict[str, Any]:
    next_state = dict(merge_state)
    next_state["sources"] = [dict(source) for source in merge_state.get("sources", [])]
    next_state["sources"][index]["status"] = status
    return next_state


def _complete_source(merge_state: dict[str, Any], index: int, *, summary: str | None = None, error: str | None = None) -> dict[str, Any]:
    next_state = dict(merge_state)
    next_state["sources"] = [dict(source) for source in merge_state.get("sources", [])]
    source = next_state["sources"][index]
    source["status"] = "failed" if error else "complete"
    source["summary"] = summary
    source["error"] = error
    next_state["completed_sources"] = sum(1 for item in next_state["sources"] if item.get("status") == "complete")
    return next_state


def _build_merge_brief(source_contexts: list[MergeSourceContext], merge_state: dict[str, Any]) -> str:
    source_rows = {source.session_key: source for source in source_contexts}
    lines = [f"Merged context prepared from {len(source_contexts)} sessions.", ""]
    for source in merge_state["sources"]:
        session_key = str(source.get("session_key") or "")
        context = source_rows[session_key]
        lines.append(f"## {context.title} (`{session_key}`)")
        if source.get("status") == "complete":
            lines.append(str(source.get("summary") or "").strip())
        else:
            lines.append(f"Summary unavailable: {source.get('error') or 'merge summary failed'}")
        state = context.state or {}
        decisions = _string_list(state.get("prior_decisions"))
        if decisions:
            lines.append("")
            lines.append("Decisions:")
            lines.extend(f"- {item}" for item in decisions[:4])
        questions = _string_list(state.get("unresolved_questions"))
        if questions:
            lines.append("")
            lines.append("Open questions:")
            lines.extend(f"- {item}" for item in questions[:4])
        lines.append("")

    conflicts = list(merge_state.get("conflicts") or [])
    if conflicts:
        lines.append("## Light Conflict Notes")
        lines.extend(f"- {conflict}" for conflict in conflicts)
        lines.append("")
    return "\n".join(lines).strip()


def _detect_conflicts(source_contexts: list[MergeSourceContext]) -> list[str]:
    buckets: dict[str, list[tuple[str, str]]] = {}
    for context in source_contexts:
        state = context.state or {}
        for decision in _string_list(state.get("prior_decisions")):
            topic = _decision_topic(decision)
            if not topic:
                continue
            buckets.setdefault(topic, []).append((context.session_key, decision))

    notes: list[str] = []
    for topic, items in buckets.items():
        unique_decisions = {decision for _, decision in items}
        if len(unique_decisions) < 2:
            continue
        rendered = "; ".join(f"{session_key}: {decision}" for session_key, decision in items[:3])
        notes.append(f"Possible disagreement around {topic}: {rendered}")
    return notes[:4]


def _decision_topic(value: str) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    if ":" in text:
        return text.split(":", 1)[0].strip()
    return " ".join(text.split()[:3]).strip()


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    rows: list[str] = []
    for item in value:
        text = str(item).strip()
        if text:
            rows.append(text)
    return rows


def _public_merge_state(merge_state: dict[str, Any]) -> dict[str, Any]:
    sources = []
    for source in merge_state.get("sources", []):
        if not isinstance(source, dict):
            continue
        sources.append(
            {
                "sessionKey": str(source.get("session_key") or ""),
                "title": str(source.get("title") or ""),
                "status": str(source.get("status") or "pending"),
                "summary": str(source.get("summary")) if source.get("summary") is not None else None,
                "error": str(source.get("error")) if source.get("error") is not None else None,
                "decisionCount": int(source.get("decision_count") or 0),
                "openQuestionCount": int(source.get("open_question_count") or 0),
            }
        )
    return {
        "status": str(merge_state.get("status") or "pending"),
        "sourceSessionKeys": [str(value) for value in merge_state.get("source_session_keys", []) if str(value).strip()],
        "totalSources": int(merge_state.get("total_sources") or len(sources)),
        "completedSources": int(merge_state.get("completed_sources") or 0),
        "startedAt": str(merge_state.get("started_at") or ""),
        "completedAt": str(merge_state.get("completed_at")) if merge_state.get("completed_at") is not None else None,
        "briefRunId": str(merge_state.get("brief_run_id")) if merge_state.get("brief_run_id") is not None else None,
        "briefArtifactId": str(merge_state.get("brief_artifact_id")) if merge_state.get("brief_artifact_id") is not None else None,
        "conflicts": [str(value) for value in merge_state.get("conflicts", []) if str(value).strip()],
        "sources": sources,
    }


async def _emit_merge_update(
    emit_event: SideEventEmit,
    session_key: str,
    merge_state: dict[str, Any],
    message: dict[str, Any] | None = None,
) -> None:
    payload: dict[str, Any] = {
        "sessionKey": session_key,
        "mergeState": _public_merge_state(merge_state),
    }
    if message is not None:
        payload["message"] = message
    try:
        await emit_event("sessions.merge.updated", payload)
    except Exception:
        return
