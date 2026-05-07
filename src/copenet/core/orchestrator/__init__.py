"""CopeNet orchestrator: session resolution, provider execution, event fanout."""

from __future__ import annotations

import asyncio
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable

from copenet.core.apps import AppStore
from copenet.core.harness import ChatHarness
from copenet.core.messaging import MessagingConfigStore, TelegramSessionRouteStore
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
from copenet.core.orchestrator.runtime import send_chat as send_chat_impl
from copenet.core.orchestrator.titles import generate_title as generate_title_impl, schedule_title_generation as schedule_title_generation_impl
from copenet.core.profile import PatProfileService
from copenet.providers import Provider
from copenet.core.runtime import ArtifactStore, RunStore
from copenet.core.sessions import SessionStateStore, SessionStore, TranscriptStore, to_public_message
from copenet.core.tools import ToolExecutionContext, ToolPolicy, ToolRegistry
from copenet._paths import default_artifacts_dir, default_pat_profile_dir, default_session_state_dir, default_sessions_dir


ChatEmit = Callable[[dict], Awaitable[None]]
SideEventEmit = Callable[[str, dict], Awaitable[None]]


@dataclass(frozen=True)
class ChatSendRequest:
    """Normalized chat send request."""

    session_key: str
    message: str
    idempotency_key: str | None = None
    provider: str = "codex-cli"
    model: str | None = None
    system_prompt_id: str | None = None
    task_prompt_id: str | None = None
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
        self._run_store = RunStore(root_dir=base / "runs")
        self._pulse_store = PulseStore(path=base / "pulses.json")
        self._messaging_store = MessagingConfigStore(path=base / "messaging.json")
        self._route_store = TelegramSessionRouteStore(path=base / "telegram-routes.json")
        profile_overlay_dir = default_pat_profile_dir() if os.environ.get("COPNET_DATA_DIR", "").strip() else base / "profile"
        self._profile_service = PatProfileService(run_store=self._run_store, overlay_dir=profile_overlay_dir)
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
