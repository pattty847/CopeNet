"""Whisper-backed transcription helpers for CopeNet."""

from __future__ import annotations

import asyncio
import gc
from pathlib import Path
import shutil
import subprocess
import threading
import time
from typing import AsyncIterator


FFMPEG_DOWNLOAD_URL = "https://www.ffmpeg.org/download.html"


class MediaTranscriptionError(RuntimeError):
    """Raised when a media file cannot be transcribed."""


class WhisperTranscriber:
    """Small optional Whisper wrapper with stream support."""

    def __init__(self, *, model_name: str = "base", device: str = "auto") -> None:
        self.model_name = model_name
        self.device = self._resolve_device(device)
        self.backend = "openai"
        self.model = None

    @staticmethod
    def _resolve_device(device: str) -> str:
        requested = (device or "auto").strip().lower()
        if requested and requested != "auto":
            return requested
        try:
            import torch  # type: ignore
        except Exception:  # pragma: no cover - depends on optional install
            return "cpu"
        try:
            if torch.cuda.is_available():
                return "cuda"
        except Exception:
            pass
        try:
            mps_backend = getattr(torch.backends, "mps", None)
            if mps_backend is not None and mps_backend.is_built() and mps_backend.is_available():
                return "mps"
        except Exception:
            pass
        return "cpu"

    @staticmethod
    def _ensure_ffmpeg_available() -> None:
        missing = [tool for tool in ("ffmpeg", "ffprobe") if shutil.which(tool) is None]
        if missing:
            raise MediaTranscriptionError(
                f"Missing required media tools: {', '.join(missing)}. Install FFmpeg: {FFMPEG_DOWNLOAD_URL}"
            )

    def _require_whisper(self):
        try:
            import whisper  # type: ignore
        except Exception as exc:  # pragma: no cover - depends on optional install
            raise MediaTranscriptionError(
                "openai-whisper is required for transcription when captions are unavailable. Install it with `uv sync --extra media`."
            ) from exc
        return whisper

    async def load_model(self) -> None:
        """Load the Whisper model if needed."""
        if self.model is not None:
            return
        whisper = self._require_whisper()
        loop = asyncio.get_running_loop()
        self.model = await loop.run_in_executor(None, lambda: whisper.load_model(self.model_name, device=self.device))

    def unload_model(self) -> None:
        """Release model references."""
        if self.model is not None:
            try:
                del self.model
            except Exception:
                pass
            self.model = None
        gc.collect()

    def get_audio_duration(self, audio_path: Path) -> float:
        """Return media duration in seconds when ffprobe can resolve it."""
        try:
            result = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(audio_path)],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return 0.0
        if result.returncode != 0:
            return 0.0
        try:
            return float(result.stdout.strip())
        except ValueError:
            return 0.0

    async def transcribe(self, audio_path: Path) -> str:
        """Transcribe a full media file to text."""
        chunks: list[str] = []
        async for chunk in self.transcribe_stream(audio_path):
            chunks.append(chunk)
        return " ".join(part.strip() for part in chunks if part.strip()).strip()

    async def transcribe_stream(self, audio_path: Path) -> AsyncIterator[str]:
        """Yield transcript chunks as Whisper produces them."""
        self._ensure_ffmpeg_available()
        await self.load_model()
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[str | None] = asyncio.Queue()
        errors: asyncio.Queue[BaseException] = asyncio.Queue()

        def _push(item: str | None) -> None:
            loop.call_soon_threadsafe(queue.put_nowait, item)

        def _run() -> None:
            try:
                result = self.model.transcribe(str(audio_path), fp16=self.device == "cuda")
                segments = result.get("segments") or []
                if segments:
                    for segment in segments:
                        text = str(segment.get("text") or "").strip()
                        if text:
                            _push(text)
                else:
                    text = str(result.get("text") or "").strip()
                    if text:
                        _push(text)
            except BaseException as exc:
                loop.call_soon_threadsafe(errors.put_nowait, exc)
            finally:
                _push(None)

        threading.Thread(target=_run, daemon=True).start()
        while True:
            if not errors.empty():
                raise MediaTranscriptionError(str(await errors.get()))
            item = await queue.get()
            if item is None:
                return
            yield item

    async def progress_stream(self, audio_path: Path) -> AsyncIterator[dict[str, object]]:
        """Yield progress and transcript chunk events during transcription."""
        duration = self.get_audio_duration(audio_path)
        started = time.perf_counter()
        yield {"type": "progress", "stage": "loading", "percent": 0.0, "message": f"Loading Whisper model {self.model_name}."}
        await self.load_model()
        yield {"type": "progress", "stage": "processing", "percent": 5.0, "message": f"Transcribing {audio_path.name}."}
        chunk_count = 0
        async for chunk in self.transcribe_stream(audio_path):
            chunk_count += 1
            elapsed = max(time.perf_counter() - started, 0.001)
            percent = 15.0 + min(80.0, (elapsed / max(duration, 30.0)) * 80.0) if duration else min(90.0, 15.0 + chunk_count * 5.0)
            yield {"type": "chunk", "text": chunk}
            yield {"type": "progress", "stage": "processing", "percent": round(percent, 1), "message": f"Captured {chunk_count} transcript chunks."}
