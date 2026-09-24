"""Media ingestion routes for the external app API (`/api/v1/media/*`)."""

from __future__ import annotations

import asyncio
import json
import mimetypes
from pathlib import Path
import shutil
from typing import Any, AsyncIterator, Awaitable, Callable
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from copenet.core.attachments import ChatAttachmentError, ChatAttachmentStore
from copenet.core.media import (
    MediaDependencyError,
    MediaDownloadError,
    MediaIngestionService,
    MediaTranscriptionError,
    render_transcript_attachment,
)
from copenet.host.app_api import AuthenticatedApp


class MediaImportRequest(BaseModel):
    url: str
    include_timestamps: bool = Field(default=True, alias="includeTimestamps")
    prefer_captions: bool = Field(default=True, alias="preferCaptions")


class MediaDownloadRequest(BaseModel):
    url: str


def _media_error(exc: Exception) -> HTTPException:
    detail = str(exc) or exc.__class__.__name__
    if isinstance(exc, MediaDependencyError):
        return HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=detail)
    if isinstance(exc, (MediaDownloadError, MediaTranscriptionError, ValueError)):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)
    return HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=detail)


def register_media_routes(
    router: APIRouter,
    *,
    media: MediaIngestionService,
    attachment_store: ChatAttachmentStore,
    require_media_access: Callable[..., Awaitable[AuthenticatedApp]],
) -> None:
    """Attach the media import, download, and transcription routes to `router`."""

    @router.get("/media/assets")
    async def list_media_assets(app: AuthenticatedApp = Depends(require_media_access), limit: int = 50) -> dict[str, Any]:
        return {"assets": media.list_assets(app_id=app.app_id, limit=limit)}

    @router.get("/media/assets/{asset_id}")
    async def get_media_asset(asset_id: str, app: AuthenticatedApp = Depends(require_media_access)) -> dict[str, Any]:
        asset = media.get_asset_detail(app_id=app.app_id, asset_id=asset_id)
        if asset is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="unknown media asset")
        return {"asset": asset}

    @router.post("/media/assets/{asset_id}/chat-attachment")
    async def create_media_chat_attachment(
        asset_id: str,
        app: AuthenticatedApp = Depends(require_media_access),
    ) -> dict[str, Any]:
        """Turn one asset's full transcript into a chat attachment.

        The chat send references it via `attachmentIds` like an image, and the
        orchestrator inlines the transcript text into the model input, so a
        Discuss chat sees every word rather than a summary.
        """
        asset = media.get_asset_detail(app_id=app.app_id, asset_id=asset_id)
        if asset is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="unknown media asset")
        filename, text = render_transcript_attachment(asset)
        try:
            attachment = attachment_store.save(data=text.encode("utf-8"), mime_type="text/plain", filename=filename)
        except ChatAttachmentError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        return {"attachment": attachment.to_public_dict()}

    @router.post("/media/import")
    async def import_media(body: MediaImportRequest, app: AuthenticatedApp = Depends(require_media_access)) -> dict[str, Any]:
        try:
            asset = await media.import_url(
                app_id=app.app_id,
                url=body.url,
                include_timestamps=body.include_timestamps,
                prefer_captions=body.prefer_captions,
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
    ) -> dict[str, Any]:
        safe_name = Path(file.filename or "").name.strip() or "uploaded-media"
        # A unique directory keeps the original filename, which becomes the
        # asset title; a prefixed filename leaked "upload-<hex>-" into titles.
        tmp_dir = media.store.downloads_dir / "uploads" / uuid4().hex[:12]
        tmp_dir.mkdir(parents=True, exist_ok=True)
        tmp_path = tmp_dir / safe_name
        try:
            content = await file.read()
            tmp_path.write_bytes(content)
            asset = await media.import_local_file(app_id=app.app_id, source_path=tmp_path)
        except Exception as exc:
            raise _media_error(exc) from exc
        finally:
            await file.close()
            shutil.rmtree(tmp_dir, ignore_errors=True)
        return {"asset": asset.to_public_dict()}

    @router.post("/media/transcribe")
    async def transcribe_media(
        file: UploadFile = File(...),
        app: AuthenticatedApp = Depends(require_media_access),
    ) -> dict[str, Any]:
        """Transcribe one uploaded audio clip to text without persisting an asset.

        Powers the composer voice-to-text mic: record -> upload -> Whisper -> text.
        """
        safe_name = (file.filename or "voice-clip").strip() or "voice-clip"
        tmp_dir = media.store.downloads_dir / "transcribe"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        tmp_path = tmp_dir / f"clip-{uuid4().hex[:12]}-{safe_name}"
        try:
            content = await file.read()
            tmp_path.write_bytes(content)
            text = await media.transcribe_file(source_path=tmp_path)
        except Exception as exc:
            raise _media_error(exc) from exc
        finally:
            await file.close()
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass
        return {"text": text}

    @router.get("/media/import/stream")
    async def stream_import_media(
        url: str,
        app: AuthenticatedApp = Depends(require_media_access),
        include_timestamps: bool = True,
        prefer_captions: bool = True,
    ) -> StreamingResponse:
        queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

        async def runner() -> None:
            try:
                async for event in media.stream_import_url(
                    app_id=app.app_id,
                    url=url,
                    include_timestamps=include_timestamps,
                    prefer_captions=prefer_captions,
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
