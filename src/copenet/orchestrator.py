"""CopeNet orchestrator: session resolution, provider execution, event fanout."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable
from uuid import uuid4

from copenet.providers import CodexCliProvider, Provider, ProviderEvent
from copenet.sessions import SessionStore, TranscriptMessage, TranscriptStore
from copenet.sessions.transcript_store import utc_now_iso as transcript_now
from copenet._paths import default_sessions_dir


ChatEmit = Callable[[dict], Awaitable[None]]


@dataclass(frozen=True)
class ChatSendRequest:
    """Normalized chat send request."""

    session_key: str
    message: str
    idempotency_key: str | None = None
    provider: str = "codex-cli"
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
        self._active_abort_by_run: dict[str, asyncio.Event] = {}
        self._active_run_by_session: dict[str, str] = {}
        self._idempotency_cache: dict[str, dict] = {}
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
        async with self._lock:
            cached = self._idempotency_cache.get(dedupe_key)
            if cached is not None:
                return {"runId": run_id, "status": "cached", "cached": True, "result": cached}

            active_run = self._active_run_by_session.get(session_key)
            if active_run and active_run != run_id:
                raise SessionInFlightError(active_run)

            entry = self._session_store.resolve_or_create(session_key=session_key, provider=provider_name)
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
                provider_session_id=entry.provider_session_id,
                timestamp=transcript_now(),
            ),
        )

        provider = self._providers[provider_name]
        seq = 0
        assistant_parts: list[str] = []
        prompt_to_send = message
        if request.system_prompt and request.system_prompt.strip():
            prompt_to_send = request.system_prompt.strip() + "\n\n---\n\n" + message

        try:
            async for event in provider.run(
                prompt=prompt_to_send,
                provider_session_id=entry.provider_session_id,
                abort_event=abort_event,
            ):
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
                            "message": {"role": "assistant", "content": event.text},
                        }
                    )
                elif event.kind == "final":
                    break

            assistant_text = "\n".join(part for part in assistant_parts if part).strip()
            if assistant_text:
                self._transcript_store.append_message(
                    entry.session_id,
                    TranscriptMessage(
                        run_id=run_id,
                        role="assistant",
                        content=assistant_text,
                        provider=provider_name,
                        provider_session_id=entry.provider_session_id,
                        timestamp=transcript_now(),
                        state="final",
                    ),
                )

            seq += 1
            final_payload = {
                "runId": run_id,
                "sessionKey": session_key,
                "seq": seq,
                "state": "final",
                "message": {"role": "assistant", "content": assistant_text} if assistant_text else None,
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

    def list_sessions(self) -> list[dict]:
        """List known sessions."""
        rows: list[dict] = []
        for entry in self._session_store.list_sessions():
            rows.append(
                {
                    "key": entry.session_key,
                    "sessionId": entry.session_id,
                    "provider": entry.provider,
                    "providerSessionId": entry.provider_session_id,
                    "updatedAt": entry.updated_at,
                    "inFlightRunId": entry.in_flight_run_id,
                }
            )
        return rows

    def resolve_session(self, session_key: str) -> dict | None:
        """Resolve one session by key."""
        entry = self._session_store.get(session_key.strip())
        if entry is None:
            return None
        return {
            "key": entry.session_key,
            "sessionId": entry.session_id,
            "provider": entry.provider,
            "providerSessionId": entry.provider_session_id,
            "createdAt": entry.created_at,
            "updatedAt": entry.updated_at,
            "lastRunId": entry.last_run_id,
            "inFlightRunId": entry.in_flight_run_id,
        }
