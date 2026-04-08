"""Catalog and session helpers for the orchestrator."""

from __future__ import annotations

from typing import TYPE_CHECKING

from copenet.providers import CodexCliProvider, LmStudioProvider, OllamaProvider

if TYPE_CHECKING:
    from . import Orchestrator


_PROVIDER_CLASSES: tuple[type, ...] = (CodexCliProvider, LmStudioProvider, OllamaProvider)


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
