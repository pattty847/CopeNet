"""CopeNet-native media ingestion service."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import time
from typing import Any, AsyncIterator

from .downloader import MediaDependencyError, MediaDownloadError, UniversalDownloader
from .store import MediaAssetRecord, MediaAssetStore
from .transcriber import MediaTranscriptionError, WhisperTranscriber


class MediaIngestionService:
    """Import URLs or local media files into persistent CopeNet assets."""

    def __init__(
        self,
        *,
        store: MediaAssetStore | None = None,
        downloader: UniversalDownloader | None = None,
    ) -> None:
        self.store = store or MediaAssetStore()
        self.downloader = downloader or UniversalDownloader(self.store.downloads_dir)

    async def import_url(
        self,
        *,
        app_id: str,
        url: str,
        include_timestamps: bool = True,
        prefer_captions: bool = True,
        whisper_model: str = "base",
    ) -> MediaAssetRecord:
        """Import one remote media URL into the store."""
        return await self._import_source(
            app_id=app_id,
            url=url,
            source_path=None,
            include_timestamps=include_timestamps,
            prefer_captions=prefer_captions,
            whisper_model=whisper_model,
        )

    async def import_local_file(
        self,
        *,
        app_id: str,
        source_path: Path,
        whisper_model: str = "base",
    ) -> MediaAssetRecord:
        """Import one local media file into the store."""
        return await self._import_source(
            app_id=app_id,
            url=None,
            source_path=source_path,
            include_timestamps=False,
            prefer_captions=False,
            whisper_model=whisper_model,
        )

    async def download_url(
        self,
        *,
        url: str,
    ) -> tuple[Path, dict[str, Any]]:
        """Download one remote media URL without persisting a CopeNet asset."""
        return await self.downloader.download_best_video(url)

    async def stream_import_url(
        self,
        *,
        app_id: str,
        url: str,
        include_timestamps: bool = True,
        prefer_captions: bool = True,
        whisper_model: str = "base",
    ) -> AsyncIterator[dict[str, Any]]:
        """Yield progress events while importing one URL."""
        yield {"type": "progress", "stage": "download", "percent": 2.0, "message": "Preparing media import."}
        if prefer_captions and self.downloader.is_youtube_url(url):
            yield {"type": "progress", "stage": "captions", "percent": 8.0, "message": "Checking for YouTube captions first."}
            try:
                record = await self.import_url(
                    app_id=app_id,
                    url=url,
                    include_timestamps=include_timestamps,
                    prefer_captions=True,
                    whisper_model=whisper_model,
                )
            except MediaDownloadError:
                yield {"type": "progress", "stage": "download", "percent": 12.0, "message": "Captions unavailable. Falling back to downloaded media."}
            else:
                yield {"type": "done", "asset": record.to_public_dict()}
                return

        yield {"type": "progress", "stage": "download", "percent": 20.0, "message": "Downloading media asset."}
        media_path, metadata = await self.downloader.download_best_video(url)
        yield {"type": "progress", "stage": "processing", "percent": 35.0, "message": f"Downloaded {media_path.name}."}
        transcriber = WhisperTranscriber(model_name=whisper_model)
        chunks: list[str] = []
        async for event in transcriber.progress_stream(media_path):
            if event.get("type") == "chunk":
                text = str(event.get("text") or "")
                if text:
                    chunks.append(text)
            yield event
        transcript = " ".join(part.strip() for part in chunks if part.strip()).strip()
        record = self._persist_record(
            app_id=app_id,
            source_type="url",
            source_url=url,
            source_path=None,
            title=str(metadata.get("title") or media_path.stem),
            media_path=media_path,
            transcript=transcript,
            transcript_source="whisper",
            metadata=metadata,
            duration_seconds=transcriber.get_audio_duration(media_path) or _coerce_float(metadata.get("durationSeconds")),
            latency_ms=None,
        )
        yield {"type": "done", "asset": record.to_public_dict()}

    def list_assets(self, *, app_id: str, limit: int = 50) -> list[dict[str, Any]]:
        """List public asset payloads for one app."""
        return [record.to_public_dict() for record in self.store.list_records(app_id=app_id, limit=limit)]

    def get_asset_detail(self, *, app_id: str, asset_id: str) -> dict[str, Any] | None:
        """Return one asset plus full transcript content."""
        record = self.store.get_record(asset_id)
        if record is None or record.app_id != app_id:
            return None
        payload = record.to_public_dict()
        payload["transcriptContent"] = self.store.read_transcript(record)
        return payload

    async def _import_source(
        self,
        *,
        app_id: str,
        url: str | None,
        source_path: Path | None,
        include_timestamps: bool,
        prefer_captions: bool,
        whisper_model: str,
    ) -> MediaAssetRecord:
        started = time.perf_counter()
        if url:
            if prefer_captions and self.downloader.is_youtube_url(url):
                try:
                    transcript, metadata = await self.downloader.download_youtube_captions(url, include_timestamps=include_timestamps)
                    return self._persist_record(
                        app_id=app_id,
                        source_type="url",
                        source_url=url,
                        source_path=None,
                        title=str(metadata.get("title") or "YouTube Video"),
                        media_path=None,
                        transcript=transcript,
                        transcript_source="youtube-captions",
                        metadata=metadata,
                        duration_seconds=_coerce_float(metadata.get("durationSeconds")),
                        latency_ms=_elapsed_ms(started),
                    )
                except MediaDownloadError:
                    pass
            media_path, metadata = await self.downloader.download_best_video(url)
        elif source_path is not None:
            media_path, metadata = await self.downloader.copy_local_file(source_path)
        else:
            raise MediaDownloadError("A URL or local source path is required.")

        transcriber = WhisperTranscriber(model_name=whisper_model)
        transcript = await transcriber.transcribe(media_path)
        return self._persist_record(
            app_id=app_id,
            source_type="url" if url else "file",
            source_url=url,
            source_path=str(source_path.resolve()) if source_path else None,
            title=str(metadata.get("title") or media_path.stem),
            media_path=media_path,
            transcript=transcript,
            transcript_source="whisper",
            metadata=metadata,
            duration_seconds=transcriber.get_audio_duration(media_path) or _coerce_float(metadata.get("durationSeconds")),
            latency_ms=_elapsed_ms(started),
        )

    def _persist_record(
        self,
        *,
        app_id: str,
        source_type: str,
        source_url: str | None,
        source_path: str | None,
        title: str,
        media_path: Path | None,
        transcript: str,
        transcript_source: str,
        metadata: dict[str, Any],
        duration_seconds: float | None,
        latency_ms: int | None,
    ) -> MediaAssetRecord:
        asset_id = self.store.next_asset_id()
        transcript_path = self.store.save_transcript(asset_id=asset_id, title=title, transcript=transcript)
        record = MediaAssetRecord(
            asset_id=asset_id,
            app_id=app_id,
            source_type=source_type,
            source_url=source_url,
            source_path=source_path,
            title=title,
            media_path=str(media_path.resolve()) if media_path else None,
            transcript_path=str(transcript_path.resolve()),
            transcript_source=transcript_source,
            transcript_excerpt=_excerpt(transcript),
            metadata=dict(metadata),
            duration_seconds=duration_seconds,
            latency_ms=latency_ms,
        )
        return self.store.save_record(record)


def _elapsed_ms(started: float) -> int:
    return max(1, int((time.perf_counter() - started) * 1000))


def _coerce_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _excerpt(text: str, limit: int = 220) -> str:
    compact = " ".join((text or "").split()).strip()
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "…"
