"""External app-facing REST and SSE API."""

from __future__ import annotations

import asyncio
import json
import mimetypes
import os
from dataclasses import dataclass
from typing import Any, AsyncIterator
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from copenet.core.meme_ideation import (
    MemeIdeationCandidate,
    MemeIdeationRequest,
    MemeRefinementMessage,
    MemeRefinementRequest,
    build_media_transcript_pack,
    ideate_memes,
    refine_memes,
)
from copenet.core.media import MediaDependencyError, MediaDownloadError, MediaIngestionService, MediaTranscriptionError
from copenet.core.orchestrator import ChatSendRequest, Orchestrator
from copenet.core.web_ingest import WebIngestError, WebIngestionService


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


class MemeIdeationApiRequest(BaseModel):
    topic: str | None = None
    trend_summary: str | None = Field(default=None, alias="trendSummary")
    image_springboard: str | None = Field(default=None, alias="imageSpringboard")
    tone_hints: str | list[str] | None = Field(default=None, alias="toneHints")
    requested_count: int = Field(alias="requestedCount")
    provider: str | None = None
    model: str | None = None
    preset: str | None = None
    media_asset_id: str | None = Field(default=None, alias="mediaAssetId")
    media_title: str | None = Field(default=None, alias="mediaTitle")
    media_source_url: str | None = Field(default=None, alias="mediaSourceUrl")
    media_transcript_pack: dict[str, Any] | None = Field(default=None, alias="mediaTranscriptPack")
    debug: bool = False


class MemeCandidateApiModel(BaseModel):
    direction: str
    format: str
    text: str
    optional_caption: str | None = Field(default=None, alias="optionalCaption")
    needs_visual_context: bool = Field(default=False, alias="needsVisualContext")
    notes: str | None = None


class MemeRefinementMessageApiModel(BaseModel):
    role: str
    content: str


class MemeRefinementApiRequest(MemeIdeationApiRequest):
    current_generation_summary: str | None = Field(default=None, alias="currentGenerationSummary")
    current_candidates: list[MemeCandidateApiModel] = Field(default_factory=list, alias="currentCandidates")
    history: list[MemeRefinementMessageApiModel] = Field(default_factory=list)
    message: str


class MediaImportRequest(BaseModel):
    url: str
    include_timestamps: bool = Field(default=True, alias="includeTimestamps")
    prefer_captions: bool = Field(default=True, alias="preferCaptions")
    whisper_model: str = Field(default="base", alias="whisperModel")


class MediaDownloadRequest(BaseModel):
    url: str


class TelegramInboundRequest(BaseModel):
    chat_id: str = Field(alias="chatId")
    thread_id: str | None = Field(default=None, alias="threadId")
    text: str
    title_hint: str | None = Field(default=None, alias="titleHint")
    idempotency_key: str | None = Field(default=None, alias="idempotencyKey")


class WebExtractRequest(BaseModel):
    url: str
    max_chars: int = Field(default=20000, alias="maxChars")


def create_app_router(
    orchestrator: Orchestrator,
    media_service: MediaIngestionService | None = None,
    web_ingestion_service: WebIngestionService | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["app-api"])
    media = media_service or MediaIngestionService()
    web_ingest = web_ingestion_service or WebIngestionService()
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

    async def require_gateway(authorization: str | None = Header(default=None)) -> None:
        token = _bearer_token(authorization)
        if not token:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing bearer token")
        if gateway_token and token == gateway_token:
            return
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid bearer token")

    def _mapping_for(app: AuthenticatedApp, app_session_id: str):
        mapping = orchestrator._app_store.get_mapping(app.app_id, app_session_id)
        if mapping is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="unknown session")
        return mapping

    def _web_ingest_error(exc: Exception) -> HTTPException:
        if isinstance(exc, WebIngestError):
            return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
        return HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"web ingest failed: {exc}")

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

    def _serialize_meme_candidate(candidate: MemeIdeationCandidate) -> dict[str, Any]:
        return {
            "direction": candidate.direction,
            "format": candidate.format,
            "text": candidate.text,
            "optional_caption": candidate.optional_caption,
            "needs_visual_context": candidate.needs_visual_context,
            "notes": candidate.notes,
        }

    def _resolve_media_context(
        *,
        app: AuthenticatedApp,
        media_asset_id: str | None,
        media_title: str | None,
        media_source_url: str | None,
        media_transcript_pack: dict[str, Any] | None,
    ) -> tuple[str | None, str | None, dict[str, Any] | None]:
        if media_asset_id and media_transcript_pack is None:
            asset = media.get_asset_detail(app_id=app.app_id, asset_id=media_asset_id)
            if asset is not None:
                media_title = media_title or str(asset.get("title") or "") or None
                media_source_url = media_source_url or str(asset.get("sourceUrl") or "") or None
                transcript_pack = build_media_transcript_pack(
                    title=media_title,
                    transcript=str(asset.get("transcriptContent") or ""),
                    transcript_source=str(asset.get("transcriptSource") or ""),
                    transcript_excerpt=str(asset.get("transcriptExcerpt") or ""),
                )
                media_transcript_pack = {
                    "summary": transcript_pack.summary,
                    "keyLines": list(transcript_pack.key_lines),
                    "notableQuotes": list(transcript_pack.notable_quotes),
                    "transcriptSource": asset.get("transcriptSource"),
                    "transcriptExcerpt": asset.get("transcriptExcerpt"),
                    "toneCues": list(transcript_pack.tone_cues),
                }
        return media_title, media_source_url, media_transcript_pack

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
        effective_provider = (provider or app.default_provider or "openai-codex").strip()
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

    async def _run_session_chat(
        *,
        session_key: str,
        content: str,
        provider: str | None,
        model: str | None,
        system_prompt_id: str | None,
        task_prompt_id: str | None,
        idempotency_key: str | None,
        allow_tools: bool = True,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        events: list[dict[str, Any]] = []

        async def emit(payload: dict[str, Any]) -> None:
            events.append(payload)

        result = await orchestrator.send_chat(
            ChatSendRequest(
                session_key=session_key,
                message=content,
                idempotency_key=idempotency_key,
                provider=(provider or "openai-codex").strip(),
                model=(model or "").strip() or None,
                system_prompt_id=system_prompt_id,
                task_prompt_id=task_prompt_id,
                allow_tools=allow_tools,
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
        provider = (body.provider or app.default_provider or "openai-codex").strip()
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

    @router.post("/messaging/telegram/inbound")
    async def telegram_inbound(body: TelegramInboundRequest, _: None = Depends(require_gateway)) -> dict[str, Any]:
        resolved = orchestrator.resolve_messaging_route(
            platform="telegram",
            chat_id=body.chat_id,
            thread_id=body.thread_id,
            create_if_missing=True,
            title_hint=body.title_hint,
        )
        session = resolved.get("session")
        if not isinstance(session, dict):
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="failed to resolve session")

        result, events = await _run_session_chat(
            session_key=str(session.get("key") or ""),
            content=body.text,
            provider=str(session.get("provider") or ""),
            model=str(session.get("model") or "") or None,
            system_prompt_id=str(session.get("systemPromptId") or "") or None,
            task_prompt_id=str(session.get("taskPromptId") or "") or None,
            idempotency_key=body.idempotency_key,
            allow_tools=True,
        )
        final_event = next((event for event in reversed(events) if event.get("state") in {"final", "error"}), None)
        return {
            "createdSession": bool(resolved.get("created")),
            "route": resolved.get("route"),
            "session": session,
            "run": result,
            "event": final_event,
            "events": events,
        }

    @router.post("/memes/ideate")
    async def ideate_memes_endpoint(body: MemeIdeationApiRequest, app: AuthenticatedApp = Depends(require_media_access)) -> dict[str, Any]:
        provider_name = (body.provider or app.default_provider or "lm-studio").strip()
        provider = orchestrator._providers.get(provider_name)
        if provider is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"unsupported provider: {provider_name}")
        try:
            media_title, media_source_url, media_transcript_pack = _resolve_media_context(
                app=app,
                media_asset_id=body.media_asset_id,
                media_title=body.media_title,
                media_source_url=body.media_source_url,
                media_transcript_pack=body.media_transcript_pack,
            )
            ideation_request = MemeIdeationRequest(
                topic=body.topic,
                trend_summary=body.trend_summary,
                image_springboard=body.image_springboard,
                tone_hints=body.tone_hints,
                requested_count=body.requested_count,
                provider=provider_name,
                model=body.model,
                preset=body.preset or None,
                media_asset_id=body.media_asset_id,
                media_title=media_title,
                media_source_url=media_source_url,
                media_transcript_pack=media_transcript_pack,
                debug=body.debug,
            )
            result = await ideate_memes(
                provider_name=provider_name,
                provider=provider,
                request=ideation_request,
            )
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
        payload: dict[str, Any] = {
            "candidates": [_serialize_meme_candidate(candidate) for candidate in result.candidates],
            "provider": result.provider,
            "model": result.model,
            "preset": result.preset,
            "schemaVersion": result.schema_version,
            "promptVersion": result.prompt_version,
        }
        if result.warnings:
            payload["warnings"] = result.warnings
        if result.knowledge_pack_version is not None:
            payload["knowledgePackVersion"] = result.knowledge_pack_version
        if result.judge_warnings:
            payload["judgeWarnings"] = result.judge_warnings
        if result.artifact_shell is not None:
            payload["artifactShell"] = result.artifact_shell
        if result.mutation_notes:
            payload["mutationNotes"] = result.mutation_notes
        if body.debug and result.raw_text is not None:
            payload["raw_text"] = result.raw_text
        return payload

    @router.post("/memes/refine")
    async def refine_memes_endpoint(body: MemeRefinementApiRequest, app: AuthenticatedApp = Depends(require_media_access)) -> dict[str, Any]:
        provider_name = (body.provider or app.default_provider or "lm-studio").strip()
        provider = orchestrator._providers.get(provider_name)
        if provider is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"unsupported provider: {provider_name}")
        try:
            media_title, media_source_url, media_transcript_pack = _resolve_media_context(
                app=app,
                media_asset_id=body.media_asset_id,
                media_title=body.media_title,
                media_source_url=body.media_source_url,
                media_transcript_pack=body.media_transcript_pack,
            )
            ideation_request = MemeIdeationRequest(
                topic=body.topic,
                trend_summary=body.trend_summary,
                image_springboard=body.image_springboard,
                tone_hints=body.tone_hints,
                requested_count=body.requested_count,
                provider=provider_name,
                model=body.model,
                preset=body.preset or None,
                media_asset_id=body.media_asset_id,
                media_title=media_title,
                media_source_url=media_source_url,
                media_transcript_pack=media_transcript_pack,
                debug=body.debug,
            )
            refinement_request = MemeRefinementRequest(
                ideation_request=ideation_request,
                current_generation_summary=body.current_generation_summary,
                current_candidates=tuple(
                    MemeIdeationCandidate(
                        direction=item.direction,
                        format=item.format,
                        text=item.text,
                        optional_caption=item.optional_caption,
                        needs_visual_context=item.needs_visual_context,
                        notes=item.notes,
                    )
                    for item in body.current_candidates
                ),
                chat_history=tuple(MemeRefinementMessage(role=item.role, content=item.content) for item in body.history),
                latest_user_message=body.message,
                debug=body.debug,
            )
            result = await refine_memes(
                provider_name=provider_name,
                provider=provider,
                request=refinement_request,
            )
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
        payload: dict[str, Any] = {
            "assistantReply": result.assistant_reply,
            "suggestedCandidates": [_serialize_meme_candidate(candidate) for candidate in result.suggested_candidates],
            "provider": result.provider,
            "model": result.model,
            "preset": result.preset,
            "schemaVersion": result.schema_version,
            "promptVersion": result.prompt_version,
        }
        if result.warnings:
            payload["warnings"] = result.warnings
        if result.knowledge_pack_version is not None:
            payload["knowledgePackVersion"] = result.knowledge_pack_version
        if result.judge_warnings:
            payload["judgeWarnings"] = result.judge_warnings
        if result.artifact_shell is not None:
            payload["artifactShell"] = result.artifact_shell
        if result.mutation_notes:
            payload["mutationNotes"] = result.mutation_notes
        if body.debug and result.raw_text is not None:
            payload["raw_text"] = result.raw_text
        return payload

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
                        provider=(provider or app.default_provider or "openai-codex").strip(),
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

    @router.post("/media/download")
    async def download_media(body: MediaDownloadRequest, app: AuthenticatedApp = Depends(require_media_access)) -> FileResponse:
        try:
            media_path, metadata = await media.download_url(url=body.url)
        except Exception as exc:
            raise _media_error(exc) from exc
        media_type = mimetypes.guess_type(media_path.name)[0] or "application/octet-stream"
        filename = str(metadata.get("filename") or media_path.name)
        return FileResponse(path=media_path, media_type=media_type, filename=filename)

    @router.post("/media/upload")
    async def upload_media(
        file: UploadFile = File(...),
        app: AuthenticatedApp = Depends(require_media_access),
        whisper_model: str = Query(default="base", alias="whisperModel"),
    ) -> dict[str, Any]:
        safe_name = (file.filename or "uploaded-media").strip() or "uploaded-media"
        tmp_dir = media.store.downloads_dir / "uploads"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        tmp_path = tmp_dir / f"upload-{uuid4().hex[:12]}-{safe_name}"
        try:
            content = await file.read()
            tmp_path.write_bytes(content)
            asset = await media.import_local_file(
                app_id=app.app_id,
                source_path=tmp_path,
                whisper_model=whisper_model,
            )
        except Exception as exc:
            raise _media_error(exc) from exc
        finally:
            await file.close()
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass
        return {"asset": asset.to_public_dict()}

    @router.post("/web/extract")
    async def extract_web_page(body: WebExtractRequest, app: AuthenticatedApp = Depends(require_media_access)) -> dict[str, Any]:
        try:
            result = await web_ingest.extract_url(url=body.url, max_chars=body.max_chars)
        except Exception as exc:
            raise _web_ingest_error(exc) from exc
        return {"document": result.to_public_dict()}

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
