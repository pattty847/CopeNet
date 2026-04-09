"""CopeNet orchestrator: session resolution, provider execution, event fanout."""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable

from copenet.core.harness import ChatHarness
from copenet.core.orchestrator.catalog import (
    archive_session as archive_session_record,
    build_default_provider_registry,
    create_session as create_catalog_session,
    create_session_with_profile as create_profiled_session,
    list_models as list_provider_models,
    list_providers_catalog as list_provider_catalog,
    list_sessions as list_session_catalog,
    list_tools as list_tool_catalog,
    rename_session as rename_session_record,
    resolve_session as resolve_session_record,
)
from copenet.core.orchestrator.runtime import send_chat as send_chat_impl
from copenet.core.orchestrator.titles import generate_title as generate_title_impl, schedule_title_generation as schedule_title_generation_impl
from copenet.providers import Provider
from copenet.core.sessions import SessionStore, TranscriptStore, to_public_message
from copenet.core.tools import ToolExecutionContext, ToolPolicy, ToolRegistry
from copenet._paths import default_sessions_dir


ChatEmit = Callable[[dict], Awaitable[None]]


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
        self._workdir = Path(os.environ.get("COPNET_WORKDIR") or os.getcwd()).resolve()
        self._session_store = session_store or SessionStore(path=base / "index.json")
        self._transcript_store = transcript_store or TranscriptStore(root_dir=base)
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

    async def send_chat(self, request: ChatSendRequest, emit: ChatEmit) -> dict:
        """Start one chat run and stream events through `emit` callback."""
        return await send_chat_impl(self, request, emit)

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
        )

    def rename_session(self, session_key: str, title: str | None) -> dict:
        """Rename a session title."""
        return rename_session_record(self, session_key=session_key, title=title)

    def archive_session(self, session_key: str, archived: bool = True) -> dict:
        """Archive or restore a session."""
        return archive_session_record(self, session_key=session_key, archived=archived)

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

    def resolve_session(self, session_key: str) -> dict | None:
        """Resolve one session by key."""
        return resolve_session_record(self, session_key)

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
