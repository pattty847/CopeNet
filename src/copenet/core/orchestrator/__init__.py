"""CopeNet orchestrator: session resolution, provider execution, event fanout."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable

from copenet.core.apps import AppStore
from copenet.core.harness import ChatHarness
from copenet.core.memory import MemoryService, MemoryStore
from copenet.core.permissions import PermissionStore
from copenet.core.messaging import MessagingConfigStore, TelegramSessionRouteStore
from copenet.core.nasa import NasaApodImageCache, NasaApodService, NasaApodStore
from copenet.core.orchestrator.nasa import (
    apod_image_path as apod_image_path_record,
    fetch_apod as fetch_apod_record,
    list_apods as list_apods_record,
)
from copenet.core.orchestrator.catalog import (
    archive_session as archive_session_record,
    build_default_provider_registry,
    create_session as create_catalog_session,
    create_session_with_profile as create_profiled_session,
    debug_copy_session as debug_copy_session_record,
    export_session as export_session_record,
    list_models as list_provider_models,
    list_providers_catalog as list_provider_catalog,
    list_sessions as list_session_catalog,
    list_tools as list_tool_catalog,
    rename_session as rename_session_record,
    resolve_session as resolve_session_record,
)
from copenet.core.orchestrator.merge import merge_sessions as merge_session_record, resolve_merge_state as resolve_merge_state_record
from copenet.core.orchestrator.messaging import (
    delete_messaging_route as delete_messaging_route_record,
    delete_messaging_destination as delete_messaging_destination_record,
    get_messaging_config as get_messaging_config_record,
    list_messaging_destinations as list_messaging_destinations_record,
    list_messaging_routes as list_messaging_routes_record,
    resolve_messaging_route as resolve_messaging_route_record,
    test_messaging_platform as test_messaging_platform_record,
    upsert_messaging_route as upsert_messaging_route_record,
    upsert_messaging_destination as upsert_messaging_destination_record,
    update_messaging_config as update_messaging_config_record,
)
from copenet.core.orchestrator.pulse import (
    create_pulse_from_session as create_pulse_from_session_record,
    dismiss_pulse as dismiss_pulse_record,
    list_pulses as list_pulses_record,
    save_pulses as save_pulses_record,
)
from copenet.core.pulse import PulseStore
from copenet.core.persona import PersonaHomeService, PersonaPrivacyTier
from copenet.core.orchestrator.runtime import send_chat as send_chat_impl
from copenet.core.orchestrator.titles import generate_title as generate_title_impl, schedule_title_generation as schedule_title_generation_impl
from copenet.core.profile import PatProfileService
from copenet.prompts.optimizer import optimize_prompt_variants
from copenet.providers import Provider
from copenet.core.runtime import ArtifactStore, EditBackupStore, RunStore
from copenet.core.sessions import SessionStateStore, SessionStore, TranscriptStore, to_public_message
from copenet.core.tools import ToolExecutionContext, ToolPolicy, ToolRegistry
from copenet.core.workspace_intel import WorkspaceIntelService, WorkspaceIntelStore
from copenet._paths import (
    default_artifacts_dir,
    default_pat_profile_dir,
    default_personas_dir,
    default_session_state_dir,
    default_sessions_dir,
    default_workspace_intel_path,
)


ChatEmit = Callable[[dict], Awaitable[None]]
SideEventEmit = Callable[[str, dict], Awaitable[None]]


@dataclass(frozen=True)
class ChatSendRequest:
    """Normalized chat send request."""

    session_key: str
    message: str
    idempotency_key: str | None = None
    provider: str = "openai-codex"
    model: str | None = None
    system_prompt_id: str | None = None
    task_prompt_id: str | None = None
    persona_id: str | None = None
    persona_flavor_id: str | None = None
    persona_privacy_tier: PersonaPrivacyTier | None = None
    timeout_ms: int | None = None
    system_prompt: str | None = None
    allow_tools: bool = True
    workspace_root: str | None = None


class SessionInFlightError(RuntimeError):
    """Raised when a second run is attempted on an active session."""

    def __init__(self, run_id: str) -> None:
        super().__init__(f"session is in_flight: {run_id}")
        self.run_id = run_id


class Orchestrator:
    """Coordinates providers, session store, transcript store, and run lifecycle."""

    def __init__(
        self,
        session_store: SessionStore | None = None,
        transcript_store: TranscriptStore | None = None,
        sessions_dir: Path | None = None,
        providers: dict[str, Provider] | None = None,
    ) -> None:
        base = sessions_dir if sessions_dir is not None else default_sessions_dir()
        workdir_env = os.environ.get("COPNET_WORKDIR", "").strip()
        self._workdir = Path(workdir_env or (str(base) if sessions_dir is not None else os.getcwd())).resolve()
        self._session_store = session_store or SessionStore(path=base / "index.json")
        self._transcript_store = transcript_store or TranscriptStore(root_dir=base)
        self._session_state_store = SessionStateStore(root_dir=default_session_state_dir() if sessions_dir is None else base / "state")
        self._artifact_store = ArtifactStore(root_dir=default_artifacts_dir() if sessions_dir is None else base / "artifacts")
        self._edit_backup_store = EditBackupStore(root_dir=None if sessions_dir is None else base / "edit-backups")
        self._run_store = RunStore(root_dir=base / "runs")
        self._pulse_store = PulseStore(path=base / "pulses.json")
        self._messaging_store = MessagingConfigStore(path=base / "messaging.json")
        self._route_store = TelegramSessionRouteStore(path=base / "telegram-routes.json")
        self._memory_store = MemoryStore(path=base / "memory.json")
        self._memory_service = MemoryService(self._memory_store)
        # Global operator shell allowlist (Access & Permissions — Brick E). One list
        # per data dir; consulted by the shell handler as a standing approval.
        self._permission_store = PermissionStore(path=base / "permissions.json")
        self._nasa_store = NasaApodStore(path=base / "nasa-apod.json")
        self._nasa_service = NasaApodService()
        self._nasa_image_cache = NasaApodImageCache(root_dir=base / "nasa-apod-images")
        profile_overlay_dir = default_pat_profile_dir() if os.environ.get("COPNET_DATA_DIR", "").strip() else base / "profile"
        self._profile_service = PatProfileService(run_store=self._run_store, overlay_dir=profile_overlay_dir)
        # Personas are user-level identity, NOT session data — they live at the canonical
        # global root (~/.copenet/personas, or COPNET_DATA_DIR/personas), never under
        # sessions/. Only a test that passes an explicit sessions_dir WITHOUT a COPNET_DATA_DIR
        # keeps them isolated under that dir.
        persona_isolated = sessions_dir is not None and not os.environ.get("COPNET_DATA_DIR", "").strip()
        persona_root = base / "personas" if persona_isolated else default_personas_dir()
        self._persona_service = PersonaHomeService(root_dir=persona_root)
        workspace_intel_path = default_workspace_intel_path() if sessions_dir is None else base / "workspace-intel.json"
        self._workspace_intel_store = WorkspaceIntelStore(path=workspace_intel_path)
        self._workspace_intel_service = WorkspaceIntelService(self._workspace_intel_store)
        self._app_store = AppStore(path=base / "apps.json")
        if providers is None:
            self._providers, self._provider_init_errors = build_default_provider_registry()
        else:
            self._providers = dict(providers)
            self._provider_init_errors = {}
        self._harness = ChatHarness()

        self._tool_policy = ToolPolicy()
        self._tool_registry = ToolRegistry(policy=self._tool_policy)

        self._trace_enabled = os.environ.get("COPNET_TRACE", "").strip().lower() in {"1", "true", "yes", "on"}
        self._active_abort_by_run: dict[str, asyncio.Event] = {}
        self._active_run_by_session: dict[str, str] = {}
        self._idempotency_cache: dict[str, dict] = {}
        self._background_tasks: set[asyncio.Task] = set()
        self._lock = asyncio.Lock()
        # Pending tool approvals awaiting an operator decision. Keyed by
        # approvalId -> {"event": asyncio.Event, "decision": str|None, "note": str|None}.
        self._pending_approvals: dict[str, dict] = {}

        # Crash recovery: clear any in_flight markers stranded by a previous
        # crash/kill so they can't brick the session forever, and record each as
        # an interrupted run so history isn't silently missing a turn.
        self._recover_interrupted_runs()

    def _recover_interrupted_runs(self) -> None:
        """Sweep stale in_flight markers at startup; log + record each one.

        A fresh process owns no live runs. We catch errors here so a corrupt
        index can't make the host unbootable — `_load_map` still fails loud on
        the first real session operation, with the corrupt copy already backed
        up, so the catastrophe (silent overwrite) stays closed either way.
        """
        import logging

        logger = logging.getLogger("copenet.orchestrator")
        try:
            stuck = self._session_store.clear_stale_in_flight()
        except Exception as exc:  # noqa: BLE001 — startup must not hard-crash here
            logger.warning("startup in-flight recovery skipped: %s", exc)
            return
        if not stuck:
            return

        from copenet.core.runtime import RunRecord
        from copenet.core.sessions.transcript_store import utc_now_iso

        logger.warning(
            "recovered %d session(s) stuck in_flight after an unclean shutdown: %s",
            len(stuck),
            ", ".join(key for key, *_ in stuck),
        )
        for session_key, run_id, provider, model in stuck:
            try:
                self._run_store.create(
                    RunRecord(
                        run_id=run_id,
                        session_key=session_key,
                        provider=provider,
                        model=model,
                        status="interrupted",
                        user_message="",
                        tool_execution_mode="none",
                        will_attempt_tool_loop=False,
                        completed_at=utc_now_iso(),
                        error="Run interrupted: process exited before it completed.",
                        transition_reason="process_interrupted",
                        terminal_reason="process_interrupted",
                    )
                )
            except Exception as exc:  # noqa: BLE001 — best-effort observability record
                logger.warning("could not record interrupted run %s: %s", run_id, exc)

    async def send_chat(self, request: ChatSendRequest, emit: ChatEmit, emit_event: SideEventEmit | None = None) -> dict:
        """Start one chat run and stream events through `emit` callback."""
        return await send_chat_impl(self, request, emit, emit_event=emit_event)

    def abort(self, session_key: str, run_id: str | None = None) -> dict:
        """Abort active run by run_id or session key."""
        target_run = run_id.strip() if run_id else self._active_run_by_session.get(session_key.strip())
        if not target_run:
            return {"ok": True, "aborted": False, "runIds": []}

        abort_event = self._active_abort_by_run.get(target_run)
        if abort_event is None:
            return {"ok": True, "aborted": False, "runIds": []}

        abort_event.set()
        return {"ok": True, "aborted": True, "runIds": [target_run]}

    def history(self, session_key: str, limit: int = 200) -> list[dict]:
        """Read transcript history for a session key."""
        entry = self._session_store.get(session_key.strip())
        if entry is None:
            return []
        history = self._transcript_store.read_history(session_id=entry.session_id, limit=limit)
        return [to_public_message(message) for message in history]

    def create_session(self, provider: str, model: str | None = None, key: str | None = None, title: str | None = None) -> dict:
        """Create a new session with a locked provider/model binding."""
        return create_catalog_session(self, provider=provider, model=model, key=key, title=title)

    def create_session_with_profile(
        self,
        provider: str,
        model: str | None = None,
        key: str | None = None,
        title: str | None = None,
        system_prompt_id: str | None = None,
        task_prompt_id: str | None = None,
        persona_id: str | None = None,
        persona_flavor_id: str | None = None,
        persona_privacy_tier: PersonaPrivacyTier | None = None,
        workspace_root: str | None = None,
        starter_intent: str | None = None,
    ) -> dict:
        """Create a new session with a locked provider/model/profile/task binding."""
        return create_profiled_session(
            self,
            provider=provider,
            model=model,
            key=key,
            title=title,
            system_prompt_id=system_prompt_id,
            task_prompt_id=task_prompt_id,
            persona_id=persona_id,
            persona_flavor_id=persona_flavor_id,
            persona_privacy_tier=persona_privacy_tier,
            workspace_root=self.validate_workspace_root(workspace_root) if workspace_root else None,
            starter_intent=starter_intent,
        )

    def rename_session(self, session_key: str, title: str | None) -> dict:
        """Rename a session title."""
        return rename_session_record(self, session_key=session_key, title=title)

    def archive_session(self, session_key: str, archived: bool = True) -> dict:
        """Archive or restore a session."""
        return archive_session_record(self, session_key=session_key, archived=archived)

    def debug_copy_session(self, session_key: str) -> dict:
        """Create a fresh debug copy of an existing conversation."""
        return debug_copy_session_record(self, session_key=session_key)

    def export_session(self, session_key: str) -> dict:
        """Export a session conversation for debugging or sharing."""
        return export_session_record(self, session_key=session_key)

    async def list_providers_catalog(self) -> list[dict]:
        """Registered provider ids and display labels for clients (includes init failures)."""
        return await list_provider_catalog(self)

    def list_tools(self) -> list[dict]:
        """List available CopeNet-native tool descriptors."""
        return list_tool_catalog(self)

    async def list_models(self, provider_id: str | None = None, kind: str = "chat") -> list[dict]:
        """List models for one provider or all providers."""
        return await list_provider_models(self, provider_id=provider_id, kind=kind)

    async def optimize_prompt(
        self,
        *,
        prompt: str,
        provider_id: str | None = None,
        model: str | None = None,
        custom_transform: str | None = None,
    ) -> dict:
        """Generate optimized prompt variants using one configured provider."""
        requested_provider = (provider_id or "").strip()
        provider = self._providers.get(requested_provider) if requested_provider else next(iter(self._providers.values()), None)
        if provider is None:
            if requested_provider and requested_provider in self._provider_init_errors:
                raise ValueError(self._provider_init_errors[requested_provider])
            raise ValueError("No prompt-optimization provider is available")
        result = await optimize_prompt_variants(
            provider=provider,
            prompt=prompt,
            model=model,
            custom_transform=custom_transform,
        )
        return result.to_dict()

    def list_sessions(self, include_archived: bool = False) -> list[dict]:
        """List known sessions."""
        return list_session_catalog(self, include_archived=include_archived)

    def get_messaging_config(self) -> dict:
        """Return the persisted operator messaging configuration."""
        return get_messaging_config_record(self)

    def update_messaging_config(self, *, approval_policy: dict | None = None, telegram_defaults: dict | None = None) -> dict:
        """Persist a minimal messaging configuration patch."""
        return update_messaging_config_record(self, approval_policy=approval_policy, telegram_defaults=telegram_defaults)

    def test_messaging_platform(self, platform: str = "telegram") -> dict:
        """Run a conservative local messaging config test."""
        return test_messaging_platform_record(self, platform=platform)

    def list_messaging_destinations(self) -> list[dict]:
        """Return configured messaging destinations."""
        return list_messaging_destinations_record(self)

    def upsert_messaging_destination(self, *, destination: dict) -> dict:
        """Create or update one messaging destination."""
        return upsert_messaging_destination_record(self, destination=destination)

    def delete_messaging_destination(self, *, destination_id: str) -> dict:
        """Delete one messaging destination."""
        return delete_messaging_destination_record(self, destination_id=destination_id)

    def list_messaging_routes(self) -> list[dict]:
        """Return configured Telegram chat-to-session routes."""
        return list_messaging_routes_record(self)

    def upsert_messaging_route(self, *, route: dict) -> dict:
        """Create or update one Telegram route mapping."""
        return upsert_messaging_route_record(self, route=route)

    def delete_messaging_route(self, *, route_id: str) -> dict:
        """Delete one Telegram route mapping."""
        return delete_messaging_route_record(self, route_id=route_id)

    def resolve_messaging_route(
        self,
        *,
        platform: str,
        chat_id: str,
        thread_id: str | None = None,
        create_if_missing: bool = False,
        title_hint: str | None = None,
    ) -> dict:
        """Resolve or autocreate the CopeNet session backing one messaging conversation."""
        return resolve_messaging_route_record(
            self,
            platform=platform,
            chat_id=chat_id,
            thread_id=thread_id,
            create_if_missing=create_if_missing,
            title_hint=title_hint,
        )

    def provider_auth_status(self, provider_id: str) -> dict:
        """Resolve auth status for a provider that owns local auth state."""
        provider = self._providers.get(provider_id.strip())
        auth_service = getattr(provider, "auth_service", None)
        if auth_service is None or not hasattr(auth_service, "status"):
            raise ValueError(f"provider does not expose auth management: {provider_id}")
        return auth_service.status()

    def provider_auth_begin_login(self, provider_id: str, redirect_uri: str | None = None) -> dict:
        """Start an interactive provider auth login flow."""
        provider = self._providers.get(provider_id.strip())
        auth_service = getattr(provider, "auth_service", None)
        if auth_service is None or not hasattr(auth_service, "begin_login"):
            raise ValueError(f"provider does not expose auth management: {provider_id}")
        return auth_service.begin_login(redirect_uri=redirect_uri)

    def provider_auth_complete_login(
        self,
        provider_id: str,
        *,
        login_token: str,
        redirect_url: str | None = None,
        code: str | None = None,
        state: str | None = None,
    ) -> dict:
        """Finish an interactive provider auth login flow."""
        provider = self._providers.get(provider_id.strip())
        auth_service = getattr(provider, "auth_service", None)
        if auth_service is None or not hasattr(auth_service, "complete_login"):
            raise ValueError(f"provider does not expose auth management: {provider_id}")
        return auth_service.complete_login(
            login_token=login_token,
            redirect_url=redirect_url,
            code=code,
            state=state,
        )

    def provider_auth_logout(self, provider_id: str) -> dict:
        """Clear provider-owned local auth state."""
        provider = self._providers.get(provider_id.strip())
        auth_service = getattr(provider, "auth_service", None)
        if auth_service is None or not hasattr(auth_service, "logout"):
            raise ValueError(f"provider does not expose auth management: {provider_id}")
        return auth_service.logout()

    def resolve_session(self, session_key: str) -> dict | None:
        """Resolve one session by key."""
        return resolve_session_record(self, session_key)

    async def merge_sessions(
        self,
        *,
        source_session_keys: list[str],
        provider: str,
        model: str | None,
        system_prompt_id: str | None,
        task_prompt_id: str | None,
        workspace_root: str | None,
        title: str | None = None,
        emit_event: SideEventEmit | None = None,
    ) -> dict[str, dict]:
        """Create a new merged session and begin async hydration."""
        return await merge_session_record(
            self,
            source_session_keys=source_session_keys,
            provider=provider,
            model=model,
            system_prompt_id=system_prompt_id,
            task_prompt_id=task_prompt_id,
            workspace_root=workspace_root,
            title=title,
            emit_event=emit_event,
        )

    def list_pulses(self) -> list[dict]:
        """List active Inbox pulses."""
        return list_pulses_record(self)

    def fetch_apod(self, *, date: str | None = None, refresh: bool = False) -> dict:
        """Fetch one NASA Astronomy Picture of the Day, persist it, and return it."""
        return fetch_apod_record(self, date=date, refresh=refresh)

    def list_apods(self, *, limit: int = 60) -> list[dict]:
        """List collected NASA APOD records, newest day first."""
        return list_apods_record(self, limit=limit)

    def nasa_image_path(self, date: str):
        """Return a local cached image path for an APOD date (lazily caching), or None."""
        return apod_image_path_record(self, date)

    @property
    def nasa_configured(self) -> bool:
        """True when NASA_API_KEY is present so the APOD surface can fetch."""
        return self._nasa_service.configured

    async def create_pulse_from_session(
        self,
        *,
        session_key: str,
        provider: str,
        model: str | None,
        system_prompt_id: str | None,
        task_prompt_id: str | None,
        emit_event: SideEventEmit | None = None,
    ) -> dict[str, object]:
        """Create one durable Pulse from a source session."""
        return await create_pulse_from_session_record(
            self,
            session_key=session_key,
            provider=provider,
            model=model,
            system_prompt_id=system_prompt_id,
            task_prompt_id=task_prompt_id,
            emit_event=emit_event,
        )

    async def dismiss_pulse(self, *, pulse_id: str, emit_event: SideEventEmit | None = None) -> dict[str, object]:
        """Dismiss one Pulse from the Inbox."""
        return await dismiss_pulse_record(self, pulse_id=pulse_id, emit_event=emit_event)

    async def save_pulses(
        self,
        *,
        pulse_ids: list[str],
        provider: str,
        model: str | None,
        system_prompt_id: str | None,
        task_prompt_id: str | None,
        workspace_root: str | None,
        emit_event: SideEventEmit | None = None,
    ) -> dict[str, object]:
        """Save one or more pulses into a new Agent session/workspace."""
        return await save_pulses_record(
            self,
            pulse_ids=pulse_ids,
            provider=provider,
            model=model,
            system_prompt_id=system_prompt_id,
            task_prompt_id=task_prompt_id,
            workspace_root=workspace_root,
            emit_event=emit_event,
        )

    def get_pat_profile(self) -> dict | None:
        """Return the current public Pat Profile payload, if configured."""
        profile = self._profile_service.load_profile()
        return profile.to_public_dict() if profile is not None else None

    def get_identity_prompt_payload(self) -> dict:
        """Return the current identity prompt payload used by the harness."""
        return self._profile_service.build_identity_prompt_payload(include_briefing=True).to_public_dict()

    def get_persona(self, *, provider: str | None = None, model: str | None = None, privacy_tier: PersonaPrivacyTier | None = None) -> dict:
        """Return the resolved Persona Home summary for UI clients."""
        return self._persona_service.get_summary(provider=provider, model=model, privacy_tier=privacy_tier)

    def get_persona_settings(self) -> dict:
        """Return Persona Home defaults and provider/model overrides."""
        return self._persona_service.load_settings().to_public_dict()

    def list_personas(self, *, provider: str | None = None, model: str | None = None) -> list[dict]:
        """List available personas (active one first) for the persona picker."""
        return self._persona_service.list_personas(provider=provider, model=model)

    def create_persona(self, *, persona_id: str, display_name: str | None = None) -> dict:
        """Create a new persona scaffold and return its public record."""
        return self._persona_service.create_persona(persona_id=persona_id, display_name=display_name)

    def select_persona(self, *, persona_id: str, provider: str | None = None, model: str | None = None) -> dict:
        """Activate a persona for the current runtime (overrides honored)."""
        return self._persona_service.select_persona(persona_id=persona_id, provider=provider, model=model).to_public_dict()

    def update_persona_settings(
        self,
        *,
        default_persona_id: str | None = None,
        default_privacy_tier: PersonaPrivacyTier | None = None,
        model_overrides: dict | None = None,
    ) -> dict:
        """Persist Persona Home defaults and provider/model overrides."""
        return self._persona_service.update_settings(
            default_persona_id=default_persona_id,
            default_privacy_tier=default_privacy_tier,
            model_overrides=model_overrides,
        ).to_public_dict()

    def get_persona_context(
        self,
        *,
        provider: str | None = None,
        model: str | None = None,
        privacy_tier: PersonaPrivacyTier | None = None,
        query: str = "",
    ) -> dict:
        """Return effective Persona Home prompt context for debugging and UI proof."""
        return self._persona_service.build_prompt_context(
            provider=provider or "",
            model=model,
            privacy_tier=privacy_tier,
            query=query,
        ).to_public_dict()

    async def draft_persona_flavor(self, *, provider_id: str, model: str | None = None) -> dict:
        """Ask a model to draft its own compact identity flavor without saving it."""
        provider = self._providers.get(provider_id)
        if provider is None:
            raise ValueError(f"unsupported provider: {provider_id}")
        persona_context = self._persona_service.build_prompt_context(
            provider=provider_id,
            model=model,
            privacy_tier="private",
            query="draft a model flavor",
        )
        prompt = (
            "Use this CopeNet Persona Home context as your base and draft a model-specific flavor.\n\n"
            f"{persona_context.prompt}\n\n"
            "Draft a compact CopeNet model identity flavor for yourself. "
            "Return JSON only with displayName, identityMarkdown, soulMarkdown, and notesMarkdown. "
            "Reflect the operator/workspace reality honestly. "
            "Do not invent new private memories or claim a relationship history you do not have."
        )
        abort_event = asyncio.Event()
        parts: list[str] = []
        async for event in provider.run(
            prompt=prompt,
            provider_session_id=None,
            abort_event=abort_event,
            model=model,
            system_prompt=(
                "You draft concise assistant identity files for local operator review. "
                "Use the provided Persona Home context carefully and stay grounded in the real workspace."
            ),
        ):
            if event.kind == "delta" and event.text:
                parts.append(event.text)
        raw_text = "".join(parts).strip()
        return {
            "provider": provider_id,
            "model": model,
            "draft": _parse_persona_flavor_draft(raw_text),
            "rawText": raw_text,
        }

    def save_persona_flavor(self, *, provider_id: str, model: str | None = None, draft: dict | None = None) -> dict:
        """Save an operator-approved model identity flavor."""
        return self._persona_service.save_flavor(provider=provider_id, model=model, draft=draft or {}).to_public_dict()

    def list_memory(self, *, include_archived: bool = False, category: str | None = None, limit: int = 50) -> list[dict]:
        """Return recent user-visible memory items."""
        return [
            item.to_public_dict()
            for item in self._memory_service.list_memory(
                include_archived=include_archived,
                category=category if category in {"preference", "project_convention", "ongoing_priority", "fact"} else None,
                limit=limit,
            )
        ]

    def upsert_memory(
        self,
        *,
        category: str,
        title: str,
        summary: str,
        detail: str | None = None,
        tags: list[str] | None = None,
        memory_id: str | None = None,
    ) -> dict:
        """Create or update one user-visible memory item."""
        item = self._memory_service.upsert_memory(
            memory_id=memory_id,
            category=category,  # type: ignore[arg-type]
            title=title,
            summary=summary,
            detail=detail,
            tags=tags or [],
            source="explicit",
            confidence=0.95,
        )
        return item.to_public_dict()

    def archive_memory(self, *, memory_id: str, archived: bool = True) -> dict | None:
        """Archive or restore one memory item."""
        item = self._memory_service.archive_memory(memory_id, archived=archived)
        return item.to_public_dict() if item is not None else None

    def list_profile_changelog(self, limit: int = 20) -> list[dict]:
        """Return recent Pat Profile changelog entries."""
        return [item.to_json() for item in self._profile_service.list_changelog(limit=limit)]

    def get_return_briefing(self) -> dict | None:
        """Return the latest return briefing payload, if any."""
        briefing = self._profile_service.build_return_briefing()
        return briefing.to_public_dict() if briefing is not None else None

    def validate_workspace_root(self, workspace_root: str | None) -> str:
        """Validate and normalize one session workspace root."""
        candidate = Path((workspace_root or "").strip() or str(self._workdir)).expanduser().resolve()
        if not candidate.exists():
            raise ValueError(f"workspace root not found: {candidate}")
        if not candidate.is_dir():
            raise ValueError(f"workspace root is not a directory: {candidate}")
        return str(candidate)

    def browse_workspace_root(self) -> str | None:
        """Open a macOS-native folder picker and return the chosen path."""
        script = 'set chosenFolder to choose folder with prompt "Choose CopeNet workspace root"\nPOSIX path of chosenFolder'
        try:
            completed = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError as exc:
            raise RuntimeError("native folder picker unavailable: osascript not found") from exc
        if completed.returncode != 0:
            stderr = (completed.stderr or "").strip()
            if "User canceled" in stderr:
                return None
            raise RuntimeError(stderr or "native folder picker failed")
        selected = (completed.stdout or "").strip()
        return self.validate_workspace_root(selected) if selected else None

    def get_runtime_context(
        self,
        *,
        session_key: str | None = None,
        workspace_root: str | None = None,
    ) -> dict:
        """Return the current workspace root and access-policy summary."""
        selected_root = workspace_root
        if session_key:
            entry = self._session_store.get(session_key.strip())
            if entry is not None and entry.workspace_root:
                selected_root = entry.workspace_root
        resolved_root = self.validate_workspace_root(selected_root) if selected_root else str(self._workdir)
        return {
            "workspaceRoot": resolved_root,
            "fileToolScope": "workspace_home_visible_roaming",
            "shellToolScope": "cwd_default",
            "shellAllowlist": list(self._tool_policy.shell_allowlist),
            "workspaceIntel": self._workspace_intel_service.get_summary(resolved_root),
            "note": (
                "Repo/file tools default to this home workspace. Reads outside it are allowed but should be visibly marked. "
                "Allowlisted shell commands run from this root."
            ),
        }

    def resolve_session_state(self, session_key: str) -> dict | None:
        """Resolve one structured runtime state record for a session."""
        record = self._session_state_store.get(session_key.strip())
        return record.to_json() if record is not None else None

    def resolve_merge_state(self, session_key: str) -> dict[str, object] | None:
        """Resolve one persisted merge-state payload for a merged session."""
        return resolve_merge_state_record(self, session_key)

    def list_session_artifacts(self, session_key: str, limit: int = 50) -> list[dict]:
        """List recent durable artifacts for one session."""
        return [record.to_public_dict() for record in self._artifact_store.list_for_session(session_key.strip(), limit=limit)]

    async def await_tool_approval(
        self,
        *,
        session_key: str,
        run_id: str,
        approval_id: str,
        request_payload: dict,
        emit_event,
        abort_event: "asyncio.Event",
        timeout_sec: float = 300.0,
    ) -> tuple[str, str | None]:
        """Park until the operator decides on a high-risk tool, or timeout/abort.

        Emits `approval.pending` with the ApprovalRequest, registers an event the
        decide RPC fires, and returns (decision, note). decision is one of
        'approved' | 'rejected' | 'timeout' | 'aborted'. The run stays alive
        (parked on this await) — no persist/reconstruct.
        """
        from copenet.core.sessions.transcript_store import utc_now_iso

        event = asyncio.Event()
        approval = {
            "approvalId": approval_id,
            "runId": run_id,
            "sessionKey": session_key,
            "status": "pending",
            "actionClass": "process_execution",
            "toolId": str(request_payload.get("toolId") or "shell.exec"),
            "proposedAction": {
                "description": str(request_payload.get("description") or ""),
                "target": request_payload.get("target"),
                "payload": request_payload.get("payload") or {},
            },
            "rationale": request_payload.get("rationale"),
            "createdAt": utc_now_iso(),
            "resolvedAt": None,
            "outcome": None,
        }
        # Keep the full approval payload so a reconnecting/reloaded client can
        # recover it via approvals.list — approval.pending is a one-shot push.
        self._pending_approvals[approval_id] = {"event": event, "decision": None, "note": None, "approval": approval}
        if emit_event is not None:
            await emit_event("approval.pending", {"approval": approval})

        decision = "timeout"
        note: str | None = None
        try:
            abort_wait = asyncio.create_task(abort_event.wait())
            decide_wait = asyncio.create_task(event.wait())
            done, pending = await asyncio.wait(
                {abort_wait, decide_wait}, timeout=timeout_sec, return_when=asyncio.FIRST_COMPLETED
            )
            for task in pending:
                task.cancel()
            if abort_wait in done and not event.is_set():
                decision = "aborted"
            elif event.is_set():
                entry = self._pending_approvals.get(approval_id) or {}
                decision = str(entry.get("decision") or "rejected")
                note = entry.get("note")
        finally:
            self._pending_approvals.pop(approval_id, None)

        if emit_event is not None:
            await emit_event(
                "approval.resolved",
                {"approvalId": approval_id, "runId": run_id, "sessionKey": session_key, "decision": decision},
            )
        return decision, note

    def list_pending_approvals(self) -> dict:
        """Return approvals still awaiting an operator decision.

        Bootstrap/reconnect recovery path: approval.pending is a one-shot push,
        so a client that reloads or connects mid-approval would otherwise never
        see the parked run. The run itself stays alive on its await; this just
        re-surfaces the card.
        """
        approvals = [
            entry["approval"]
            for entry in self._pending_approvals.values()
            if isinstance(entry, dict) and entry.get("approval")
        ]
        return {"approvals": approvals}

    def decide_approval(self, *, approval_id: str, decision: str, note: str | None = None) -> dict:
        """Record an operator's decision on a pending tool approval and wake the run."""
        entry = self._pending_approvals.get(approval_id.strip())
        if entry is None:
            return {"ok": False, "error": "no pending approval with that id"}
        normalized = decision.strip().lower()
        # "approved_always" approves this command AND persists it to the global
        # allowlist so it never asks again (Brick E). The gated executor handles
        # the persistence (it has the command + permission store on the context).
        if normalized not in {"approved", "rejected", "approved_always"}:
            return {"ok": False, "error": "decision must be 'approved', 'approved_always', or 'rejected'"}
        entry["decision"] = normalized
        entry["note"] = note
        event = entry.get("event")
        if isinstance(event, asyncio.Event):
            event.set()
        return {"ok": True, "approvalId": approval_id, "decision": normalized}

    # --- Global shell allowlist (Access & Permissions — Brick E/F) ---

    def list_shell_allowlist(self) -> dict:
        """Return the operator's global shell allowlist entries."""
        return {"commands": self._permission_store.list_commands()}

    def add_shell_allowlist(self, command: str) -> dict:
        """Add a command to the global shell allowlist."""
        entry = self._permission_store.add(command)
        if entry is None:
            return {"ok": False, "error": "command is required"}
        return {"ok": True, "entry": entry, "commands": self._permission_store.list_commands()}

    def remove_shell_allowlist(self, command: str) -> dict:
        """Remove a command from the global shell allowlist."""
        removed = self._permission_store.remove(command)
        return {"ok": removed, "commands": self._permission_store.list_commands()}

    def _resolve_session_workspace_root(self, session_key: str) -> Path:
        """Return the on-disk workspace root for a session (falls back to workdir)."""
        entry = self._session_store.get(session_key.strip())
        selected_root = entry.workspace_root if entry is not None and entry.workspace_root else None
        return Path(self.validate_workspace_root(selected_root) if selected_root else str(self._workdir))

    def list_session_workspace_files(self, *, session_key: str) -> dict:
        """List viewable files under a session's workspace root (read-only viewer)."""
        from copenet.core.workspace_files import list_workspace_files

        root = self._resolve_session_workspace_root(session_key)
        return {"root": str(root), "files": list_workspace_files(root)}

    def read_session_workspace_file(self, *, session_key: str, path: str) -> dict:
        """Read one file under a session's workspace root (scoped, size-capped)."""
        from copenet.core.workspace_files import read_workspace_file

        root = self._resolve_session_workspace_root(session_key)
        return read_workspace_file(root, path)

    def write_session_workspace_file(self, *, session_key: str, path: str, content: str) -> dict:
        """Operator inline-edit: write a file under a session's workspace root.

        Records a pre-edit backup keyed by the new content's digest so the change
        is revertible through the same `revert_file_edit` path as a model edit.
        """
        import hashlib
        from copenet.core.workspace_files import write_workspace_file

        root = self._resolve_session_workspace_root(session_key)
        result = write_workspace_file(root, path, content)
        before_content = result.pop("beforeContent", "")
        existed = result.pop("existed", False)
        after_digest = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
        if existed:
            self._edit_backup_store.record(
                session_key=session_key.strip(),
                path=result["path"],
                after_digest=after_digest,
                before_content=before_content,
            )
        result["digest"] = after_digest
        result["revertible"] = existed
        return result

    def _persona_root_rel(self, path: str) -> tuple[Path, str]:
        """Validate an absolute persona file path is under the persona root.

        Persona ``loadedFiles`` are absolute paths under the persona root; returns
        (root, rel_path) for reuse with the workspace file read/write helpers.
        """
        root = Path(self._persona_service.root_dir).resolve()
        candidate = Path((path or "").strip()).expanduser().resolve()
        try:
            rel = str(candidate.relative_to(root))
        except ValueError as exc:
            raise ValueError("path is outside the persona root") from exc
        return root, rel

    def read_persona_file(self, *, path: str) -> dict:
        """Read one persona file (scoped to the persona root, size-capped)."""
        from copenet.core.workspace_files import read_workspace_file

        root, rel = self._persona_root_rel(path)
        return read_workspace_file(root, rel)

    def write_persona_file(self, *, path: str, content: str) -> dict:
        """Operator inline-edit of a persona file (scoped to the persona root).

        Records a pre-edit backup under a persona-scoped key so the change is
        revertible through the same machinery as workspace edits.
        """
        import hashlib
        from copenet.core.workspace_files import write_workspace_file

        root, rel = self._persona_root_rel(path)
        result = write_workspace_file(root, rel, content)
        before_content = result.pop("beforeContent", "")
        existed = result.pop("existed", False)
        after_digest = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
        if existed:
            self._edit_backup_store.record(
                session_key="__persona__",
                path=rel,
                after_digest=after_digest,
                before_content=before_content,
            )
        result["digest"] = after_digest
        result["revertible"] = existed
        return result

    def revert_file_edit(self, *, session_key: str, path: str, after_digest: str) -> dict:
        """Undo a model's write/edit by restoring the recorded pre-edit content.

        Operator-initiated (not a model tool), keyed by (session_key, path,
        after_digest). Refuses unless the file is still in the exact state the
        edit left it, so a newer change is never silently clobbered.
        """
        import hashlib

        session_key = session_key.strip()
        rel_path = path.strip()
        after_digest = after_digest.strip()
        if not session_key or not rel_path or not after_digest:
            return {"ok": False, "error": "session_key, path, and after_digest are required"}

        entry = self._session_store.get(session_key)
        selected_root = entry.workspace_root if entry is not None and entry.workspace_root else None
        root = Path(self.validate_workspace_root(selected_root) if selected_root else str(self._workdir))
        target = (root / rel_path).resolve()
        try:
            target.relative_to(root.resolve())
        except ValueError:
            return {"ok": False, "error": "path is outside the session workspace"}
        if not target.is_file():
            return {"ok": False, "error": f"file not found: {rel_path}"}

        current = target.read_text(encoding="utf-8", errors="replace")
        current_digest = hashlib.sha256(current.encode("utf-8")).hexdigest()[:16]
        if current_digest != after_digest:
            return {
                "ok": False,
                "error": "file changed since this edit; not reverting",
                "path": rel_path,
            }

        record = self._edit_backup_store.find(session_key=session_key, path=rel_path, after_digest=after_digest)
        if record is None:
            return {"ok": False, "error": "no backup found for this edit", "path": rel_path}

        target.write_text(record.before_content, encoding="utf-8")
        self._edit_backup_store.mark_reverted(session_key=session_key, path=rel_path, after_digest=after_digest)
        new_digest = hashlib.sha256(record.before_content.encode("utf-8")).hexdigest()[:16]
        return {"ok": True, "path": rel_path, "newDigest": new_digest}

    def list_session_runs(self, session_key: str, limit: int = 50) -> list[dict]:
        """List recent durable run records for one session."""
        return [record.to_public_dict() for record in self._run_store.list_for_session(session_key.strip(), limit=limit)]

    def resolve_session_run(self, session_key: str, run_id: str) -> dict | None:
        """Resolve one durable run record for a session."""
        record = self._run_store.get(session_key.strip(), run_id.strip())
        return record.to_public_dict() if record is not None else None

    def register_app(
        self,
        *,
        app_id: str,
        display_name: str | None = None,
        token: str | None = None,
        default_provider: str | None = None,
        default_model: str | None = None,
        allow_tools: bool = False,
    ) -> tuple[dict, str]:
        """Register an external app and return the stored metadata plus plain token."""
        entry, plain_token = self._app_store.register_app(
            app_id=app_id,
            display_name=display_name,
            token=token,
            default_provider=default_provider,
            default_model=default_model,
            allow_tools=allow_tools,
        )
        return {
            "appId": entry.app_id,
            "displayName": entry.display_name,
            "createdAt": entry.created_at,
            "updatedAt": entry.updated_at,
            "defaultProvider": entry.default_provider,
            "defaultModel": entry.default_model,
            "allowTools": entry.allow_tools,
        }, plain_token

    @staticmethod
    def _session_payload(entry) -> dict:
        from copenet.core.orchestrator.catalog import session_payload

        return session_payload(entry)

    def _schedule_title_generation(
        self,
        session_key: str,
        provider_name: str,
        model: str | None,
        first_user_message: str,
        first_assistant_message: str,
    ) -> None:
        schedule_title_generation_impl(
            self,
            session_key=session_key,
            provider_name=provider_name,
            model=model,
            first_user_message=first_user_message,
            first_assistant_message=first_assistant_message,
        )

    async def _generate_title(
        self,
        provider_name: str,
        model: str | None,
        first_user_message: str,
        first_assistant_message: str,
    ) -> str | None:
        return await generate_title_impl(
            self,
            provider_name=provider_name,
            model=model,
            first_user_message=first_user_message,
            first_assistant_message=first_assistant_message,
        )


def _parse_persona_flavor_draft(raw_text: str) -> dict:
    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        parsed = {}
    if not isinstance(parsed, dict):
        parsed = {}
    return {
        "displayName": str(parsed.get("displayName") or parsed.get("name") or "Model Flavor").strip(),
        "identityMarkdown": str(parsed.get("identityMarkdown") or parsed.get("identity") or raw_text or "# Model Flavor").strip(),
        "soulMarkdown": str(parsed.get("soulMarkdown") or parsed.get("soul") or "").strip(),
        "notesMarkdown": str(parsed.get("notesMarkdown") or parsed.get("notes") or "").strip(),
    }
