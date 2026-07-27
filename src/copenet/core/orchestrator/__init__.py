"""CopeNet orchestrator: session resolution, provider execution, event fanout."""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable

from copenet.core.apps import AppStore
from copenet.core.attachments import ChatAttachmentStore
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
from copenet.core.orchestrator.merge import merge_sessions as merge_session_record
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
from copenet.core.orchestrator.facade_apps import AppFacadeMixin
from copenet.core.orchestrator.facade_approvals import ApprovalPermissionFacadeMixin
from copenet.core.orchestrator.facade_runtime_workspace import RuntimeWorkspaceFacadeMixin
from copenet.core.orchestrator.facade_identity import IdentityFacadeMixin
from copenet.core.orchestrator.facade_messaging import MessagingFacadeMixin
from copenet.core.orchestrator.facade_provider_auth import ProviderAuthFacadeMixin
from copenet.core.briefing import ReturnBriefingService
from copenet.core.user_notes import UserNotesService, UserNotesStore
from copenet.prompts.optimizer import optimize_prompt_variants
from copenet.providers import Provider
from copenet.core.runtime import ArtifactStore, EditBackupStore, RunStore
from copenet.core.sessions import SessionStateStore, SessionStore, TranscriptStore, to_public_message
from copenet.core.tools import ToolPolicy, ToolRegistry
from copenet.core.workspace_intel import WorkspaceIntelService, WorkspaceIntelStore
from copenet._paths import (
    default_artifacts_dir,
    default_chat_attachments_dir,
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
    # Chat attachment ids (resolved to inline images for the model). Tuple keeps
    # the frozen dataclass hashable; default empty for text-only sends.
    attachment_ids: tuple[str, ...] = ()
    # Structured operator intent for this turn. These ids are validated against
    # the registry and Access policy before they influence the hidden prompt.
    requested_tool_ids: tuple[str, ...] = ()
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


class Orchestrator(IdentityFacadeMixin, MessagingFacadeMixin, ProviderAuthFacadeMixin, RuntimeWorkspaceFacadeMixin, ApprovalPermissionFacadeMixin, AppFacadeMixin):
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
        self._chat_attachment_store = ChatAttachmentStore(root_dir=default_chat_attachments_dir() if sessions_dir is None else base / "attachments")
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
        self._briefing_service = ReturnBriefingService(run_store=self._run_store)
        # Personas are user-level identity, NOT session data — they live at the canonical
        # global root (~/.copenet/personas, or COPNET_DATA_DIR/personas), never under
        # sessions/. Only a test that passes an explicit sessions_dir WITHOUT a COPNET_DATA_DIR
        # keeps them isolated under that dir.
        persona_isolated = sessions_dir is not None and not os.environ.get("COPNET_DATA_DIR", "").strip()
        persona_root = base / "personas" if persona_isolated else default_personas_dir()
        self._persona_service = PersonaHomeService(root_dir=persona_root)
        self._user_notes_store = UserNotesStore(path=base / "user-notes.json")
        self._user_notes_service = UserNotesService(
            store=self._user_notes_store,
            persona_service=self._persona_service,
        )
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
        from copenet.core.fleet import FleetCoordinator

        self._fleet = FleetCoordinator(self, root_dir=base / "fleet")

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

    # --- Global shell allowlist (Access & Permissions — Brick E/F) ---

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
