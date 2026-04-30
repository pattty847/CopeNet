"""Catalog and session helpers for the orchestrator."""

from __future__ import annotations

import os
import json
from typing import Any
from typing import TYPE_CHECKING

from copenet.providers import CodexCliProvider, LmStudioProvider, OllamaProvider, OpenAICodexProvider, Provider

if TYPE_CHECKING:
    from . import Orchestrator


_PROVIDER_CLASSES: tuple[type, ...] = (CodexCliProvider, OpenAICodexProvider, LmStudioProvider, OllamaProvider)


def build_default_provider_registry() -> tuple[dict[str, Provider], dict[str, str]]:
    providers: dict[str, Provider] = {}
    init_errors: dict[str, str] = {}
    try:
        providers["codex-cli"] = CodexCliProvider()
    except Exception as exc:
        init_errors["codex-cli"] = str(exc)
    providers["openai-codex"] = OpenAICodexProvider()
    providers["lm-studio"] = LmStudioProvider(
        base_url=os.environ.get("COPNET_LM_STUDIO_BASE_URL", "http://127.0.0.1:1234")
    )
    providers["ollama"] = OllamaProvider(
        base_url=os.environ.get("COPNET_OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    )
    return providers, init_errors


def label_for_provider_id(provider_id: str) -> str:
    for cls in _PROVIDER_CLASSES:
        if getattr(cls, "name", None) == provider_id:
            return str(getattr(cls, "display_name", provider_id))
    return provider_id.replace("-", " ").replace("_", " ").title()


def session_payload(entry) -> dict:
    return {
        "key": entry.session_key,
        "sessionId": entry.session_id,
        "title": entry.title,
        "provider": entry.provider,
        "model": entry.model,
        "systemPromptId": entry.system_prompt_id,
        "taskPromptId": entry.task_prompt_id,
        "archived": entry.archived,
        "providerSessionId": entry.provider_session_id,
        "createdAt": entry.created_at,
        "updatedAt": entry.updated_at,
        "lastRunId": entry.last_run_id,
        "inFlightRunId": entry.in_flight_run_id,
    }


def create_session(orchestrator: "Orchestrator", provider: str, model: str | None = None, key: str | None = None, title: str | None = None) -> dict:
    return create_session_with_profile(
        orchestrator,
        provider=provider,
        model=model,
        key=key,
        title=title,
        system_prompt_id=None,
        task_prompt_id=None,
    )


def create_session_with_profile(
    orchestrator: "Orchestrator",
    provider: str,
    model: str | None = None,
    key: str | None = None,
    title: str | None = None,
    system_prompt_id: str | None = None,
    task_prompt_id: str | None = None,
) -> dict:
    if provider not in orchestrator._providers:
        init_error = orchestrator._provider_init_errors.get(provider)
        if init_error:
            raise RuntimeError(f"provider unavailable: {provider} ({init_error})")
        raise ValueError(f"unsupported provider: {provider}")
    session_key = key.strip() if key and key.strip() else orchestrator._session_store.create_generated_session_key(provider, model)
    entry = orchestrator._session_store.create_session(
        session_key=session_key,
        provider=provider,
        model=model,
        title=title,
        system_prompt_id=system_prompt_id,
        task_prompt_id=task_prompt_id,
    )
    return session_payload(entry)


def rename_session(orchestrator: "Orchestrator", session_key: str, title: str | None) -> dict:
    entry = orchestrator._session_store.rename_session(session_key=session_key, title=title)
    return session_payload(entry)


def archive_session(orchestrator: "Orchestrator", session_key: str, archived: bool = True) -> dict:
    entry = orchestrator._session_store.set_archived(session_key=session_key, archived=archived)
    return session_payload(entry)


async def list_providers_catalog(orchestrator: "Orchestrator") -> list[dict]:
    ids = sorted(set(orchestrator._providers) | set(orchestrator._provider_init_errors))
    rows: list[dict] = []
    for pid in ids:
        inst = orchestrator._providers.get(pid)
        if inst is not None:
            rows.append(await inst.describe())
        else:
            err = orchestrator._provider_init_errors.get(pid) or ""
            label = label_for_provider_id(pid)
            rows.append({"id": pid, "displayName": label, "available": False, "error": err})
    return rows


def list_tools(orchestrator: "Orchestrator") -> list[dict]:
    return orchestrator._tool_registry.list_public_tools()


async def list_models(orchestrator: "Orchestrator", provider_id: str | None = None, kind: str = "chat") -> list[dict]:
    provider_ids = [provider_id] if provider_id else sorted(orchestrator._providers)
    rows: list[dict] = []
    for pid in provider_ids:
        inst = orchestrator._providers.get(pid)
        if inst is None:
            continue
        try:
            models = await inst.list_models()
        except Exception:
            continue
        for model in models:
            if kind == "chat" and model.kind != "chat":
                continue
            rows.append(
                {
                    "id": model.id,
                    "displayName": model.display_name,
                    "provider": model.provider,
                    "description": model.description,
                    "kind": model.kind,
                    "capabilities": model.capabilities or {},
                    "recommendedFor": model.recommended_for or [],
                    "metadata": model.metadata or {},
                }
            )
    return rows


def list_sessions(orchestrator: "Orchestrator", include_archived: bool = False) -> list[dict]:
    rows: list[dict] = []
    for entry in orchestrator._session_store.list_sessions(include_archived=include_archived):
        rows.append(session_payload(entry))
    return rows


def resolve_session(orchestrator: "Orchestrator", session_key: str) -> dict | None:
    entry = orchestrator._session_store.get(session_key.strip())
    if entry is None:
        return None
    return session_payload(entry)


def debug_copy_session(orchestrator: "Orchestrator", session_key: str) -> dict:
    source = orchestrator._session_store.get(session_key.strip())
    if source is None:
        raise KeyError(f"unknown session_key: {session_key.strip()}")

    title_prefix = source.title or source.session_key
    copied = orchestrator._session_store.create_session(
        session_key=orchestrator._session_store.create_generated_session_key(source.provider, source.model),
        provider=source.provider,
        model=source.model,
        title=f"Debug Copy — {title_prefix}",
        system_prompt_id=source.system_prompt_id,
        task_prompt_id=source.task_prompt_id,
    )

    copied_count = orchestrator._transcript_store.copy_history(source.session_id, copied.session_id)
    copied_runs = orchestrator._run_store.clone_session(source.session_key, copied.session_key)

    source_state = orchestrator._session_state_store.get(source.session_key)
    artifact_id_map: dict[str, str] = {}
    source_artifacts = orchestrator._artifact_store.list_for_session(source.session_key, limit=500)
    for artifact in source_artifacts:
        cloned = orchestrator._artifact_store.create(
            session_key=copied.session_key,
            run_id=artifact.run_id,
            artifact_type=artifact.type,
            title=artifact.title,
            body=artifact.body,
            source_asset_ids=list(artifact.source_asset_ids),
            source_artifact_ids=[artifact_id_map.get(value, value) for value in artifact.source_artifact_ids],
            metadata={**artifact.metadata, "clonedFromArtifactId": artifact.artifact_id},
        )
        artifact_id_map[artifact.artifact_id] = cloned.artifact_id

    if source_state is not None:
        orchestrator._session_state_store.save(
            source_state.__class__(
                session_key=copied.session_key,
                task_summary=source_state.task_summary,
                goals=list(source_state.goals),
                active_entities=list(source_state.active_entities),
                working_set_refs=[
                    artifact_id_map.get(value, value)
                    for value in source_state.working_set_refs
                ],
                constraints=list(source_state.constraints),
                unresolved_questions=list(source_state.unresolved_questions),
                prior_decisions=list(source_state.prior_decisions),
                plan_snapshot=dict(source_state.plan_snapshot),
                relevant_asset_ids=list(source_state.relevant_asset_ids),
                relevant_artifact_ids=[
                    artifact_id_map.get(value, value)
                    for value in source_state.relevant_artifact_ids
                ],
                created_at=source_state.created_at,
                updated_at=source_state.updated_at,
            )
        )

    payload = session_payload(copied)
    payload["debugCopy"] = {
        "sourceSessionKey": source.session_key,
        "copiedMessages": copied_count,
        "copiedArtifacts": len(source_artifacts),
        "copiedRuns": copied_runs,
    }
    return payload


def export_session(orchestrator: "Orchestrator", session_key: str) -> dict[str, Any]:
    entry = orchestrator._session_store.get(session_key.strip())
    if entry is None:
        raise KeyError(f"unknown session_key: {session_key.strip()}")

    messages = orchestrator.history(entry.session_key, limit=100000)
    markdown_lines = [
        f"# Conversation Export: {entry.title or entry.session_key}",
        "",
        f"- Session key: `{entry.session_key}`",
        f"- Provider: `{entry.provider}`",
        f"- Model: `{entry.model or 'default'}`",
        f"- Profile: `{entry.system_prompt_id or 'none'}`",
        f"- Task mode: `{entry.task_prompt_id or 'none'}`",
        "",
    ]
    for message in messages:
        role = str(message.get("role") or "unknown").upper()
        timestamp = str(message.get("timestamp") or "")
        markdown_lines.append(f"## {role}")
        if timestamp:
            markdown_lines.append(f"_Timestamp: {timestamp}_")
            markdown_lines.append("")
        markdown_lines.append(str(message.get("content") or ""))
        tool_execution = message.get("toolExecution")
        if isinstance(tool_execution, dict) and tool_execution:
            markdown_lines.append("")
            markdown_lines.append("```json")
            markdown_lines.append(json.dumps(tool_execution, ensure_ascii=False, indent=2))
            markdown_lines.append("```")
        markdown_lines.append("")

    return {
        "session": session_payload(entry),
        "messages": messages,
        "markdown": "\n".join(markdown_lines).strip() + "\n",
    }
