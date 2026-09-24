"""MLX Whisper transcription for CopeNet media imports and the composer mic.

One warm model serves every caller. It loads on first use, stays resident while
work keeps arriving, and unloads after `COPNET_WHISPER_IDLE_SECONDS` of quiet so
an idle host gives the memory back. MLX runs Whisper on the Apple GPU; the
default checkpoint is large-v3-turbo (large-v3 accuracy, a fraction of the
decoder cost).
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from functools import partial
import gc
import os
from pathlib import Path
import shutil
import subprocess
import time
from typing import Any, AsyncIterator


FFMPEG_DOWNLOAD_URL = "https://www.ffmpeg.org/download.html"
DEFAULT_WHISPER_REPO = "mlx-community/whisper-large-v3-turbo"
DEFAULT_IDLE_UNLOAD_SECONDS = 600.0
# Short names accepted by COPNET_WHISPER_MODEL. Anything containing "/" is a
# Hugging Face repo id and is used as-is.
WHISPER_REPO_ALIASES = {
    "turbo": DEFAULT_WHISPER_REPO,
    "large-v3-turbo": DEFAULT_WHISPER_REPO,
    "large-v3": "mlx-community/whisper-large-v3-mlx",
}
# Rough MLX turbo speed on Apple Silicon, in audio seconds per wall second.
# Only drives the progress estimate while a transcription is running.
_ESTIMATED_REALTIME_FACTOR = 15.0
_PROGRESS_INTERVAL_SECONDS = 1.5
# MLX binds GPU streams to the thread that created them: weights loaded on one
# thread and used on another abort the whole process ("There is no Stream(gpu,
# 1) in current thread"). Every MLX call runs on this one thread. It is
# process-wide because mlx_whisper's ModelHolder cache is process-wide too.
_MLX_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="mlx-whisper")


class MediaTranscriptionError(RuntimeError):
    """Raised when a media file cannot be transcribed."""


def resolve_whisper_repo(model_name: str) -> str:
    """Map a COPNET_WHISPER_MODEL value to an MLX Hugging Face repo id."""
    name = model_name.strip()
    if not name:
        return DEFAULT_WHISPER_REPO
    if "/" in name:
        return name
    return WHISPER_REPO_ALIASES.get(name, f"mlx-community/whisper-{name}-mlx")


def configured_whisper_repo() -> str:
    return resolve_whisper_repo(os.environ.get("COPNET_WHISPER_MODEL", ""))


def configured_idle_unload_seconds() -> float:
    raw = os.environ.get("COPNET_WHISPER_IDLE_SECONDS", "").strip()
    return float(raw) if raw else DEFAULT_IDLE_UNLOAD_SECONDS


class WhisperTranscriber:
    """One shared, lazily loaded MLX Whisper model with idle unload."""

    def __init__(self, *, model_repo: str | None = None, idle_unload_seconds: float | None = None) -> None:
        self.model_repo = model_repo or configured_whisper_repo()
        self.idle_unload_seconds = (
            configured_idle_unload_seconds() if idle_unload_seconds is None else idle_unload_seconds
        )
        self.model: Any = None
        self._lock = asyncio.Lock()
        self._last_used = 0.0
        self._idle_handle: asyncio.TimerHandle | None = None

    @property
    def model_label(self) -> str:
        return self.model_repo.rsplit("/", 1)[-1]

    @staticmethod
    def _ensure_ffmpeg_available() -> None:
        missing = [tool for tool in ("ffmpeg", "ffprobe") if shutil.which(tool) is None]
        if missing:
            raise MediaTranscriptionError(
                f"Missing required media tools: {', '.join(missing)}. Install FFmpeg: {FFMPEG_DOWNLOAD_URL}"
            )

    @staticmethod
    def _require_mlx_whisper():
        try:
            import mlx.core as mx  # type: ignore
            import mlx_whisper  # type: ignore
            from mlx_whisper.transcribe import ModelHolder  # type: ignore
        except Exception as exc:  # pragma: no cover - depends on Apple Silicon install
            raise MediaTranscriptionError(
                "mlx-whisper is required for transcription when captions are unavailable. "
                "It runs on Apple Silicon only; install it with `uv sync --extra media`."
            ) from exc
        return mx, mlx_whisper, ModelHolder

    async def load_model(self) -> None:
        """Load the Whisper weights if they are not already resident."""
        if self.model is not None:
            return
        mx, _mlx_whisper, model_holder = self._require_mlx_whisper()
        # ModelHolder is mlx_whisper's own cache; warming it here means
        # mlx_whisper.transcribe() reuses these weights instead of reloading.
        self.model = await _run_on_mlx_thread(partial(model_holder.get_model, self.model_repo, mx.float16))

    def unload_model(self) -> None:
        """Drop the weights and return MLX's cached GPU buffers to the system."""
        if self.model is None:
            return
        self.model = None
        mx, _mlx_whisper, model_holder = self._require_mlx_whisper()
        model_holder.model = None
        model_holder.model_path = None
        gc.collect()
        mx.clear_cache()

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

    def _transcribe_blocking(self, audio_path: Path) -> list[str]:
        _mx, mlx_whisper, _model_holder = self._require_mlx_whisper()
        result = mlx_whisper.transcribe(
            str(audio_path),
            path_or_hf_repo=self.model_repo,
            condition_on_previous_text=True,
            verbose=None,
        )
        segments = [str(segment.get("text") or "").strip() for segment in result.get("segments") or []]
        segments = [text for text in segments if text]
        if not segments:
            text = str(result.get("text") or "").strip()
            segments = [text] if text else []
        return segments

    async def transcribe_segments(self, audio_path: Path) -> list[str]:
        """Transcribe one file and return its segment texts in order.

        Calls are serialized: one GPU model, one job at a time.
        """
        self._ensure_ffmpeg_available()
        async with self._lock:
            self._cancel_idle_unload()
            try:
                await self.load_model()
                return await _run_on_mlx_thread(partial(self._transcribe_blocking, audio_path))
            except MediaTranscriptionError:
                raise
            except Exception as exc:
                raise MediaTranscriptionError(str(exc) or exc.__class__.__name__) from exc
            finally:
                self._last_used = time.monotonic()
                self._schedule_idle_unload()

    async def transcribe(self, audio_path: Path) -> str:
        """Transcribe a full media file to text."""
        return " ".join(await self.transcribe_segments(audio_path)).strip()

    async def progress_stream(self, audio_path: Path) -> AsyncIterator[dict[str, object]]:
        """Yield progress events while transcribing, then the transcript chunks."""
        duration = self.get_audio_duration(audio_path)
        if self.model is None:
            yield {"type": "progress", "stage": "loading", "percent": 0.0, "message": f"Loading Whisper {self.model_label}."}
        started = time.perf_counter()
        expected_seconds = max(duration / _ESTIMATED_REALTIME_FACTOR, 5.0) if duration else 30.0
        task = asyncio.create_task(self.transcribe_segments(audio_path))
        while not task.done():
            await asyncio.wait({task}, timeout=_PROGRESS_INTERVAL_SECONDS)
            if task.done():
                break
            elapsed = time.perf_counter() - started
            percent = 5.0 + 90.0 * min(0.95, elapsed / expected_seconds)
            yield {
                "type": "progress",
                "stage": "processing",
                "percent": round(percent, 1),
                "message": f"Transcribing {audio_path.name} ({int(elapsed)}s).",
            }
        segments = task.result()
        for text in segments:
            yield {"type": "chunk", "text": text}
        yield {"type": "progress", "stage": "processing", "percent": 100.0, "message": f"Transcribed {len(segments)} segments."}

    def _cancel_idle_unload(self) -> None:
        if self._idle_handle is not None:
            self._idle_handle.cancel()
            self._idle_handle = None

    def _schedule_idle_unload(self) -> None:
        self._cancel_idle_unload()
        loop = asyncio.get_running_loop()
        self._idle_handle = loop.call_later(
            self.idle_unload_seconds, lambda: loop.create_task(self._unload_if_idle())
        )

    async def _unload_if_idle(self) -> None:
        async with self._lock:
            # A job may have run while this callback waited on the lock.
            if time.monotonic() - self._last_used < self.idle_unload_seconds:
                return
            await _run_on_mlx_thread(self.unload_model)


async def _run_on_mlx_thread(call):
    return await asyncio.get_running_loop().run_in_executor(_MLX_EXECUTOR, call)
