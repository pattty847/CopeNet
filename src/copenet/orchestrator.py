"""CopeNet orchestrator: session resolution, provider execution, event fanout."""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable
from uuid import uuid4

from copenet.harness import ChatHarness
from copenet.providers import CodexCliProvider, LmStudioProvider, OllamaProvider, Provider, ProviderEvent
from copenet.sessions import SessionStore, TranscriptMessage, TranscriptStore
from copenet.sessions.transcript_store import utc_now_iso as transcript_now
from copenet._paths import default_sessions_dir


ChatEmit = Callable[[dict], Awaitable[None]]

# Add each concrete provider class so the UI can show display_name even when __init__ fails.
_PROVIDER_CLASSES: tuple[type, ...] = (CodexCliProvider, LmStudioProvider, OllamaProvider)


def _label_for_provider_id(provider_id: str) -> str:
    for cls in _PROVIDER_CLASSES:
        if getattr(cls, "name", None) == provider_id:
            return str(getattr(cls, "display_name", provider_id))
    return provider_id.replace("-", " ").replace("_", " ").title()


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
    ) -> None:
        base = sessions_dir if sessions_dir is not None else default_sessions_dir()
        self._session_store = session_store or SessionStore(path=base / "index.json")
        self._transcript_store = transcript_store or TranscriptStore(root_dir=base)
        self._providers: dict[str, Provider] = {}
        self._provider_init_errors: dict[str, str] = {}
        try:
            self._providers["codex-cli"] = CodexCliProvider()
        except Exception as exc:
            self._provider_init_errors["codex-cli"] = str(exc)
        self._providers["lm-studio"] = LmStudioProvider(
            base_url=os.environ.get("COPNET_LM_STUDIO_BASE_URL", "http://127.0.0.1:1234")
        )
        self._providers["ollama"] = OllamaProvider(
            base_url=os.environ.get("COPNET_OLLAMA_BASE_URL", "http://127.0.0.1:11434")
        )
        self._harness = ChatHarness()
        self._active_abort_by_run: dict[str, asyncio.Event] = {}
        self._active_run_by_session: dict[str, str] = {}
        self._idempotency_cache: dict[str, dict] = {}
        self._background_tasks: set[asyncio.Task] = set()
        self._lock = asyncio.Lock()

    async def send_chat(self, request: ChatSendRequest, emit: ChatEmit) -> dict:
        """Start one chat run and stream events through `emit` callback."""
        session_key = request.session_key.strip()
        message = request.message.strip()
        if not session_key:
            raise ValueError("session_key is required")
        if not message:
            raise ValueError("message is required")

        run_id = request.idempotency_key.strip() if request.idempotency_key else str(uuid4())
        provider_name = request.provider.strip() or "codex-cli"
        if provider_name not in self._providers:
            init_error = self._provider_init_errors.get(provider_name)
            if init_error:
                raise RuntimeError(f"provider unavailable: {provider_name} ({init_error})")
            raise ValueError(f"unsupported provider: {provider_name}")

        dedupe_key = f"chat:{run_id}"
        prior_history = self.history(session_key=session_key, limit=2)
        is_first_turn = len(prior_history) == 0
        async with self._lock:
            cached = self._idempotency_cache.get(dedupe_key)
            if cached is not None:
                return {"runId": run_id, "status": "cached", "cached": True, "result": cached}

            active_run = self._active_run_by_session.get(session_key)
            if active_run and active_run != run_id:
                raise SessionInFlightError(active_run)

            entry = self._session_store.resolve_or_create(
                session_key=session_key,
                provider=provider_name,
                model=request.model,
                system_prompt_id=request.system_prompt_id,
                task_prompt_id=request.task_prompt_id,
            )
            entry = self._session_store.assert_session_binding(
                session_key=session_key,
                provider=provider_name,
                model=request.model,
                system_prompt_id=request.system_prompt_id,
                task_prompt_id=request.task_prompt_id,
            )
            self._session_store.mark_run_started(session_key=session_key, run_id=run_id)
            abort_event = asyncio.Event()
            self._active_abort_by_run[run_id] = abort_event
            self._active_run_by_session[session_key] = run_id

        self._transcript_store.append_message(
            entry.session_id,
            TranscriptMessage(
                run_id=run_id,
                role="user",
                content=message,
                provider=provider_name,
                model=request.model,
                provider_session_id=entry.provider_session_id,
                timestamp=transcript_now(),
            ),
        )

        provider = self._providers[provider_name]
        seq = 0
        assistant_parts: list[str] = []
        try:
            plan, event_stream = await self._harness.run_turn(
                provider=provider,
                prompt=message,
                provider_session_id=entry.provider_session_id,
                abort_event=abort_event,
                model=request.model,
                system_prompt=request.system_prompt,
            )
            async for event in event_stream:
                if event.provider_session_id and event.provider_session_id != entry.provider_session_id:
                    entry = self._session_store.update_provider_session_id(
                        session_key=session_key,
                        provider_session_id=event.provider_session_id,
                    )

                if event.kind == "delta" and event.text:
                    assistant_parts.append(event.text)
                    seq += 1
                    await emit(
                        {
                            "runId": run_id,
                            "sessionKey": session_key,
                            "seq": seq,
                            "state": "delta",
                            "message": {
                                "role": "assistant",
                                "content": event.text,
                                "provider": provider_name,
                                "model": request.model,
                            },
                            "provider": provider_name,
                            "model": request.model,
                            "capabilities": {
                                "toolCalls": plan.capability_profile.tool_calls,
                            },
                        }
                    )
                elif event.kind == "final":
                    break

            assistant_text = "".join(part for part in assistant_parts if part).strip()
            if assistant_text:
                self._transcript_store.append_message(
                    entry.session_id,
                    TranscriptMessage(
                        run_id=run_id,
                        role="assistant",
                        content=assistant_text,
                        provider=provider_name,
                        model=request.model,
                        provider_session_id=entry.provider_session_id,
                        timestamp=transcript_now(),
                        state="final",
                    ),
                )
                if is_first_turn and not (entry.title or "").strip():
                    self._schedule_title_generation(
                        session_key=session_key,
                        provider_name=provider_name,
                        model=request.model,
                        first_user_message=message,
                        first_assistant_message=assistant_text,
                    )

            seq += 1
            final_payload = {
                "runId": run_id,
                "sessionKey": session_key,
                "seq": seq,
                "state": "final",
                "message": {
                    "role": "assistant",
                    "content": assistant_text,
                    "provider": provider_name,
                    "model": request.model,
                }
                if assistant_text
                else None,
                "provider": provider_name,
                "model": request.model,
                "capabilities": {
                    "toolCalls": plan.capability_profile.tool_calls,
                },
            }
            await emit(final_payload)
            async with self._lock:
                self._idempotency_cache[dedupe_key] = final_payload
            return {"runId": run_id, "status": "ok"}
        except Exception as exc:
            seq += 1
            error_payload = {
                "runId": run_id,
                "sessionKey": session_key,
                "seq": seq,
                "state": "error",
                "errorMessage": str(exc),
                "provider": provider_name,
                "model": request.model,
            }
            await emit(error_payload)
            async with self._lock:
                self._idempotency_cache[dedupe_key] = error_payload
            return {"runId": run_id, "status": "error", "summary": str(exc)}
        finally:
            async with self._lock:
                self._active_abort_by_run.pop(run_id, None)
                if self._active_run_by_session.get(session_key) == run_id:
                    self._active_run_by_session.pop(session_key, None)
            self._session_store.mark_run_finished(session_key=session_key, run_id=run_id)

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
        return self._transcript_store.read_history(session_id=entry.session_id, limit=limit)

    def create_session(self, provider: str, model: str | None = None, key: str | None = None, title: str | None = None) -> dict:
        """Create a new session with a locked provider/model binding."""
        return self.create_session_with_profile(
            provider=provider,
            model=model,
            key=key,
            title=title,
            system_prompt_id=None,
        )

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
        if provider not in self._providers:
            init_error = self._provider_init_errors.get(provider)
            if init_error:
                raise RuntimeError(f"provider unavailable: {provider} ({init_error})")
            raise ValueError(f"unsupported provider: {provider}")
        session_key = key.strip() if key and key.strip() else self._session_store.create_generated_session_key(provider, model)
        entry = self._session_store.create_session(
            session_key=session_key,
            provider=provider,
            model=model,
            title=title,
            system_prompt_id=system_prompt_id,
            task_prompt_id=task_prompt_id,
        )
        return self._session_payload(entry)

    def rename_session(self, session_key: str, title: str | None) -> dict:
        """Rename a session title."""
        entry = self._session_store.rename_session(session_key=session_key, title=title)
        return self._session_payload(entry)

    def archive_session(self, session_key: str, archived: bool = True) -> dict:
        """Archive or restore a session."""
        entry = self._session_store.set_archived(session_key=session_key, archived=archived)
        return self._session_payload(entry)

    async def list_providers_catalog(self) -> list[dict]:
        """Registered provider ids and display labels for clients (includes init failures)."""
        ids = sorted(set(self._providers) | set(self._provider_init_errors))
        rows: list[dict] = []
        for pid in ids:
            inst = self._providers.get(pid)
            if inst is not None:
                rows.append(await inst.describe())
            else:
                err = self._provider_init_errors.get(pid) or ""
                label = _label_for_provider_id(pid)
                rows.append({"id": pid, "displayName": label, "available": False, "error": err})
        return rows

    async def list_models(self, provider_id: str | None = None, kind: str = "chat") -> list[dict]:
        """List models for one provider or all providers."""
        provider_ids = [provider_id] if provider_id else sorted(self._providers)
        rows: list[dict] = []
        for pid in provider_ids:
            inst = self._providers.get(pid)
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

    def list_sessions(self, include_archived: bool = False) -> list[dict]:
        """List known sessions."""
        rows: list[dict] = []
        for entry in self._session_store.list_sessions(include_archived=include_archived):
            rows.append(self._session_payload(entry))
        return rows

    def resolve_session(self, session_key: str) -> dict | None:
        """Resolve one session by key."""
        entry = self._session_store.get(session_key.strip())
        if entry is None:
            return None
        return self._session_payload(entry)

    @staticmethod
    def _session_payload(entry) -> dict:
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

    def _schedule_title_generation(
        self,
        session_key: str,
        provider_name: str,
        model: str | None,
        first_user_message: str,
        first_assistant_message: str,
    ) -> None:
        async def run() -> None:
            try:
                title = await self._generate_title(
                    provider_name=provider_name,
                    model=model,
                    first_user_message=first_user_message,
                    first_assistant_message=first_assistant_message,
                )
                if not title:
                    return
                current = self._session_store.get(session_key)
                if current is None or (current.title or "").strip():
                    return
                self._session_store.rename_session(session_key=session_key, title=title)
            except Exception:
                return

        task = asyncio.create_task(run())
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    async def _generate_title(
        self,
        provider_name: str,
        model: str | None,
        first_user_message: str,
        first_assistant_message: str,
    ) -> str | None:
        provider = self._providers.get(provider_name)
        if provider is None:
            return None

        title_prompt = (
            "Generate a concise chat session title from the conversation.\n"
            "Return only the title as plain text.\n"
            "Rules: 2 to 5 words, no quotes, no markdown, no list markers, avoid trailing punctuation.\n\n"
            f"User message:\n{first_user_message}\n\n"
            f"Assistant response:\n{first_assistant_message}\n"
        )
        abort_event = asyncio.Event()
        parts: list[str] = []
        async for event in provider.run(
            prompt=title_prompt,
            provider_session_id=None,
            abort_event=abort_event,
            model=model,
            system_prompt="You generate short session titles. Return only the title text.",
        ):
            if event.kind == "delta" and event.text:
                parts.append(event.text)
            elif event.kind == "final":
                break
        title = "".join(parts).strip()
        if not title:
            return None
        title = title.replace("\n", " ").strip().strip("\"'` ")
        title = " ".join(title.split())
        if not title:
            return None
        return title[:64].rstrip(" .,:;!-")
