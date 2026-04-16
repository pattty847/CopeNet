"""External app-facing REST and SSE API."""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from typing import Any, AsyncIterator
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from copenet.core.media import MediaDependencyError, MediaDownloadError, MediaIngestionService, MediaTranscriptionError
from copenet.core.orchestrator import ChatSendRequest, Orchestrator


@dataclass(frozen=True)
class AuthenticatedApp:
    app_id: str
    display_name: str
    default_provider: str | None
    default_model: str | None
    allow_tools: bool


class SessionCreateRequest(BaseModel):
    id: str | None = None
    title: str | None = None
    provider: str | None = None
    model: str | None = None
    system_prompt_id: str | None = Field(default=None, alias="systemPromptId")
    task_prompt_id: str | None = Field(default=None, alias="taskPromptId")


class SessionUpdateRequest(BaseModel):
    title: str | None = None
    archived: bool | None = None


class MessageSendRequest(BaseModel):
    content: str
    provider: str | None = None
    model: str | None = None
    system_prompt_id: str | None = Field(default=None, alias="systemPromptId")
    task_prompt_id: str | None = Field(default=None, alias="taskPromptId")
    idempotency_key: str | None = Field(default=None, alias="idempotencyKey")


class MediaImportRequest(BaseModel):
    url: str
    include_timestamps: bool = Field(default=True, alias="includeTimestamps")
    prefer_captions: bool = Field(default=True, alias="preferCaptions")
    whisper_model: str = Field(default="base", alias="whisperModel")


def create_app_router(orchestrator: Orchestrator, media_service: MediaIngestionService | None = None) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["app-api"])
    media = media_service or MediaIngestionService()
    gateway_token = os.environ.get("COPNET_TOKEN", "dev-token").strip()

    def _bearer_token(authorization: str | None) -> str:
        if not authorization:
            return ""
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer":
            return ""
        return token.strip()

    async def require_app(authorization: str | None = Header(default=None)) -> AuthenticatedApp:
        token = _bearer_token(authorization)
        if not token:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing bearer token")
        entry = orchestrator._app_store.authenticate_token(token)
        if entry is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid bearer token")
        return AuthenticatedApp(
            app_id=entry.app_id,
            display_name=entry.display_name,
            default_provider=entry.default_provider,
            default_model=entry.default_model,
            allow_tools=entry.allow_tools,
        )

    async def require_media_access(authorization: str | None = Header(default=None)) -> AuthenticatedApp:
        token = _bearer_token(authorization)
        if not token:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing bearer token")
        if gateway_token and token == gateway_token:
            return AuthenticatedApp(
                app_id="copenet-web",
                display_name="CopeNet Web",
                default_provider=None,
                default_model=None,
                allow_tools=True,
            )
        return await require_app(authorization)

    def _mapping_for(app: AuthenticatedApp, app_session_id: str):
        mapping = orchestrator._app_store.get_mapping(app.app_id, app_session_id)
        if mapping is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="unknown session")
        return mapping

    def _public_session(app_session_id: str, session: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": app_session_id,
            "title": session.get("title"),
            "provider": session.get("provider"),
            "model": session.get("model"),
            "systemPromptId": session.get("systemPromptId"),
            "taskPromptId": session.get("taskPromptId"),
            "archived": session.get("archived", False),
            "createdAt": session.get("createdAt"),
            "updatedAt": session.get("updatedAt"),
            "lastRunId": session.get("lastRunId"),
            "inFlightRunId": session.get("inFlightRunId"),
        }

    def _public_chat_event(app_session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        event = dict(payload)
        event["sessionKey"] = app_session_id
        return event

    def _media_error(exc: Exception) -> HTTPException:
        detail = str(exc) or exc.__class__.__name__
        if isinstance(exc, MediaDependencyError):
            return HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=detail)
        if isinstance(exc, (MediaDownloadError, MediaTranscriptionError, ValueError)):
            return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)
        return HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=detail)

    async def _run_chat(
        app: AuthenticatedApp,
        *,
        app_session_id: str,
        content: str,
        provider: str | None,
        model: str | None,
        system_prompt_id: str | None,
        task_prompt_id: str | None,
        idempotency_key: str | None,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        mapping = _mapping_for(app, app_session_id)
        effective_provider = (provider or app.default_provider or "codex-cli").strip()
        effective_model = (model or app.default_model or "").strip() or None
        events: list[dict[str, Any]] = []

        async def emit(payload: dict[str, Any]) -> None:
            events.append(_public_chat_event(app_session_id, payload))

        result = await orchestrator.send_chat(
            ChatSendRequest(
                session_key=mapping.internal_session_key,
                message=content,
                idempotency_key=idempotency_key,
                provider=effective_provider,
                model=effective_model,
                system_prompt_id=system_prompt_id,
                task_prompt_id=task_prompt_id,
                allow_tools=app.allow_tools,
            ),
            emit=emit,
        )
        return result, events

    @router.get("/providers")
    async def list_providers(_: AuthenticatedApp = Depends(require_app)) -> dict[str, Any]:
        return {"providers": await orchestrator.list_providers_catalog()}

    @router.get("/models")
    async def list_models(provider: str | None = None, _: AuthenticatedApp = Depends(require_app)) -> dict[str, Any]:
        return {"models": await orchestrator.list_models(provider_id=provider, kind="chat")}

    @router.get("/sessions")
    async def list_sessions(app: AuthenticatedApp = Depends(require_app), include_archived: bool = False) -> dict[str, Any]:
        sessions: list[dict[str, Any]] = []
        for mapping in orchestrator._app_store.list_mappings_for_app(app.app_id):
            session = orchestrator.resolve_session(mapping.internal_session_key)
            if not session:
                continue
            if session.get("archived") and not include_archived:
                continue
            sessions.append(_public_session(mapping.app_session_id, session))
        return {"sessions": sessions}

    @router.post("/sessions", status_code=status.HTTP_201_CREATED)
    async def create_session(body: SessionCreateRequest, app: AuthenticatedApp = Depends(require_app)) -> dict[str, Any]:
        app_session_id = (body.id or str(uuid4())).strip()
        if not app_session_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="session id is required")
        existing = orchestrator._app_store.get_mapping(app.app_id, app_session_id)
        if existing is not None:
            session = orchestrator.resolve_session(existing.internal_session_key)
            if not session:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="session mapping is stale")
            return {"session": _public_session(app_session_id, session)}
        provider = (body.provider or app.default_provider or "codex-cli").strip()
        model = (body.model or app.default_model or "").strip() or None
        internal_key = f"app-{app.app_id}-{uuid4().hex[:12]}"
        session = orchestrator.create_session_with_profile(
            provider=provider,
            model=model,
            key=internal_key,
            title=body.title,
            system_prompt_id=body.system_prompt_id,
            task_prompt_id=body.task_prompt_id,
        )
        orchestrator._app_store.create_mapping(
            app_id=app.app_id,
            app_session_id=app_session_id,
            internal_session_key=internal_key,
        )
        return {"session": _public_session(app_session_id, session)}

    @router.get("/sessions/{session_id}")
    async def get_session(session_id: str, app: AuthenticatedApp = Depends(require_app)) -> dict[str, Any]:
        mapping = _mapping_for(app, session_id)
        session = orchestrator.resolve_session(mapping.internal_session_key)
        if not session:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="unknown session")
        return {"session": _public_session(session_id, session)}

    @router.patch("/sessions/{session_id}")
    async def update_session(session_id: str, body: SessionUpdateRequest, app: AuthenticatedApp = Depends(require_app)) -> dict[str, Any]:
        mapping = _mapping_for(app, session_id)
        if body.title is not None:
            session = orchestrator.rename_session(mapping.internal_session_key, body.title)
        else:
            session = orchestrator.resolve_session(mapping.internal_session_key)
        if body.archived is not None:
            session = orchestrator.archive_session(mapping.internal_session_key, archived=body.archived)
        if not session:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="unknown session")
        return {"session": _public_session(session_id, session)}

    @router.get("/sessions/{session_id}/messages")
    async def get_messages(session_id: str, app: AuthenticatedApp = Depends(require_app), limit: int = 200) -> dict[str, Any]:
        mapping = _mapping_for(app, session_id)
        messages = orchestrator.history(mapping.internal_session_key, limit=limit)
        return {"sessionId": session_id, "messages": messages}

    @router.post("/sessions/{session_id}/messages")
    async def send_message(session_id: str, body: MessageSendRequest, app: AuthenticatedApp = Depends(require_app)) -> dict[str, Any]:
        result, events = await _run_chat(
            app,
            app_session_id=session_id,
            content=body.content,
            provider=body.provider,
            model=body.model,
            system_prompt_id=body.system_prompt_id,
            task_prompt_id=body.task_prompt_id,
            idempotency_key=body.idempotency_key,
        )
        final_event = next((event for event in reversed(events) if event.get("state") in {"final", "error"}), None)
        return {
            "run": result,
            "event": final_event,
            "events": events,
        }

    @router.get("/sessions/{session_id}/messages/stream")
    async def stream_message(
        session_id: str,
        content: str,
        app: AuthenticatedApp = Depends(require_app),
        provider: str | None = None,
        model: str | None = None,
        system_prompt_id: str | None = None,
        task_prompt_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> StreamingResponse:
        _mapping_for(app, session_id)
        queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

        async def emit(payload: dict[str, Any]) -> None:
            await queue.put(_public_chat_event(session_id, payload))

        async def runner() -> None:
            try:
                mapping = _mapping_for(app, session_id)
                await orchestrator.send_chat(
                    ChatSendRequest(
                        session_key=mapping.internal_session_key,
                        message=content,
                        idempotency_key=idempotency_key,
                        provider=(provider or app.default_provider or "codex-cli").strip(),
                        model=(model or app.default_model or "").strip() or None,
                        system_prompt_id=system_prompt_id,
                        task_prompt_id=task_prompt_id,
                        allow_tools=app.allow_tools,
                    ),
                    emit=emit,
                )
            except Exception as exc:
                await queue.put({"state": "error", "errorMessage": str(exc), "sessionKey": session_id, "seq": 1, "runId": idempotency_key or ""})
            finally:
                await queue.put(None)

        asyncio.create_task(runner())

        async def event_stream() -> AsyncIterator[bytes]:
            while True:
                item = await queue.get()
                if item is None:
                    yield b"event: done\ndata: {}\n\n"
                    return
                yield f"event: chat\ndata: {json.dumps(item, ensure_ascii=False)}\n\n".encode("utf-8")

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    @router.post("/runs/{run_id}/cancel")
    async def cancel_run(run_id: str, app: AuthenticatedApp = Depends(require_app)) -> dict[str, Any]:
        session_key = ""
        for mapping in orchestrator._app_store.list_mappings_for_app(app.app_id):
            session = orchestrator.resolve_session(mapping.internal_session_key)
            if session and session.get("inFlightRunId") == run_id:
                session_key = mapping.internal_session_key
                break
        return orchestrator.abort(session_key=session_key, run_id=run_id)

    @router.get("/media/assets")
    async def list_media_assets(app: AuthenticatedApp = Depends(require_media_access), limit: int = 50) -> dict[str, Any]:
        return {"assets": media.list_assets(app_id=app.app_id, limit=limit)}

    @router.get("/media/assets/{asset_id}")
    async def get_media_asset(asset_id: str, app: AuthenticatedApp = Depends(require_media_access)) -> dict[str, Any]:
        asset = media.get_asset_detail(app_id=app.app_id, asset_id=asset_id)
        if asset is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="unknown media asset")
        return {"asset": asset}

    @router.post("/media/import")
    async def import_media(body: MediaImportRequest, app: AuthenticatedApp = Depends(require_media_access)) -> dict[str, Any]:
        try:
            asset = await media.import_url(
                app_id=app.app_id,
                url=body.url,
                include_timestamps=body.include_timestamps,
                prefer_captions=body.prefer_captions,
                whisper_model=body.whisper_model,
            )
        except Exception as exc:
            raise _media_error(exc) from exc
        return {"asset": asset.to_public_dict()}

    @router.get("/media/import/stream")
    async def stream_import_media(
        url: str,
        app: AuthenticatedApp = Depends(require_media_access),
        include_timestamps: bool = True,
        prefer_captions: bool = True,
        whisper_model: str = "base",
    ) -> StreamingResponse:
        queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

        async def runner() -> None:
            try:
                async for event in media.stream_import_url(
                    app_id=app.app_id,
                    url=url,
                    include_timestamps=include_timestamps,
                    prefer_captions=prefer_captions,
                    whisper_model=whisper_model,
                ):
                    await queue.put(event)
            except Exception as exc:
                await queue.put({"type": "error", "message": str(exc)})
            finally:
                await queue.put(None)

        asyncio.create_task(runner())

        async def event_stream() -> AsyncIterator[bytes]:
            while True:
                item = await queue.get()
                if item is None:
                    yield b"event: done\ndata: {}\n\n"
                    return
                event_name = str(item.get("type") or "message")
                yield f"event: {event_name}\ndata: {json.dumps(item, ensure_ascii=False)}\n\n".encode("utf-8")

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    return router
