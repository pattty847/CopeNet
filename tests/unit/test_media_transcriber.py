from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from copenet.core.media.transcriber import (
    DEFAULT_WHISPER_REPO,
    MediaTranscriptionError,
    TranscriptSegment,
    WhisperTranscriber,
    resolve_whisper_repo,
)


def _fake_transcriber(
    monkeypatch: pytest.MonkeyPatch,
    *,
    idle_unload_seconds: float = 60.0,
    segments: list[str] | None = None,
    error: Exception | None = None,
) -> tuple[WhisperTranscriber, dict[str, int]]:
    transcriber = WhisperTranscriber(model_repo="mlx-community/whisper-tiny", idle_unload_seconds=idle_unload_seconds)
    calls = {"load": 0, "unload": 0, "transcribe": 0}
    monkeypatch.setattr(transcriber, "_ensure_ffmpeg_available", lambda: None)
    monkeypatch.setattr(transcriber, "get_audio_duration", lambda _path: 0.0)

    async def fake_load_model() -> None:
        if transcriber.model is None:
            calls["load"] += 1
            transcriber.model = object()

    def fake_unload_model() -> None:
        calls["unload"] += 1
        transcriber.model = None

    def fake_transcribe_blocking(_path: Path) -> list[TranscriptSegment]:
        calls["transcribe"] += 1
        if error is not None:
            raise error
        texts = segments or ["alpha", "beta"]
        # Segments 65 seconds apart so timestamps cross a minute boundary.
        return [TranscriptSegment(start_seconds=index * 65.0, text=text) for index, text in enumerate(texts)]

    monkeypatch.setattr(transcriber, "load_model", fake_load_model)
    monkeypatch.setattr(transcriber, "unload_model", fake_unload_model)
    monkeypatch.setattr(transcriber, "_transcribe_blocking", fake_transcribe_blocking)
    return transcriber, calls


@pytest.mark.asyncio
async def test_transcription_keeps_whisper_warm_between_imports(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    transcriber, calls = _fake_transcriber(monkeypatch)

    first = await transcriber.transcribe(tmp_path / "one.mp3")
    second = await transcriber.transcribe(tmp_path / "two.mp3")

    assert first == second == "alpha beta"
    assert calls == {"load": 1, "unload": 0, "transcribe": 2}
    assert transcriber.model is not None


@pytest.mark.asyncio
async def test_idle_window_unloads_whisper(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    transcriber, calls = _fake_transcriber(monkeypatch, idle_unload_seconds=0.05)

    await transcriber.transcribe(tmp_path / "clip.mp3")
    await asyncio.sleep(0.2)

    assert calls["unload"] == 1
    assert transcriber.model is None


@pytest.mark.asyncio
async def test_work_inside_idle_window_postpones_unload(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    transcriber, calls = _fake_transcriber(monkeypatch, idle_unload_seconds=0.2)

    await transcriber.transcribe(tmp_path / "one.mp3")
    await asyncio.sleep(0.12)
    await transcriber.transcribe(tmp_path / "two.mp3")
    await asyncio.sleep(0.12)
    assert calls["unload"] == 0

    await asyncio.sleep(0.2)
    assert calls["unload"] == 1
    assert calls["load"] == 1


@pytest.mark.asyncio
async def test_transcription_failure_is_wrapped_and_still_schedules_unload(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    transcriber, calls = _fake_transcriber(monkeypatch, idle_unload_seconds=0.05, error=ValueError("bad audio"))

    with pytest.raises(MediaTranscriptionError, match="bad audio"):
        await transcriber.transcribe(tmp_path / "clip.mp3")
    await asyncio.sleep(0.2)

    assert calls["unload"] == 1


@pytest.mark.asyncio
async def test_progress_stream_reports_loading_then_transcript_chunks(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    transcriber, _calls = _fake_transcriber(monkeypatch, segments=["first line", "second line"])

    events = [event async for event in transcriber.progress_stream(tmp_path / "clip.mp3")]

    assert [event["type"] for event in events] == ["progress", "chunk", "chunk", "progress"]
    assert events[0]["stage"] == "loading"
    assert [event["text"] for event in events if event["type"] == "chunk"] == ["first line", "second line"]
    assert events[-1]["percent"] == 100.0

    warm_events = [event async for event in transcriber.progress_stream(tmp_path / "clip.mp3")]
    assert warm_events[0]["type"] == "chunk"

    stamped = [event async for event in transcriber.progress_stream(tmp_path / "clip.mp3", include_timestamps=True)]
    assert [event["text"] for event in stamped if event["type"] == "chunk"] == [
        "[00:00:00] first line",
        "[00:01:05] second line",
    ]


@pytest.mark.asyncio
async def test_imports_get_one_timestamped_line_per_segment_and_the_mic_gets_plain_text(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    transcriber, _calls = _fake_transcriber(monkeypatch, segments=["It is day out.", "Now it is night."])

    assert await transcriber.transcribe(tmp_path / "clip.mp3", include_timestamps=True) == (
        "[00:00:00] It is day out.\n[00:01:05] Now it is night."
    )
    assert await transcriber.transcribe(tmp_path / "clip.mp3") == "It is day out. Now it is night."


def test_whisper_model_setting_accepts_short_names_and_repo_ids() -> None:
    assert resolve_whisper_repo("") == DEFAULT_WHISPER_REPO
    assert resolve_whisper_repo("turbo") == "mlx-community/whisper-large-v3-turbo"
    assert resolve_whisper_repo("small.en") == "mlx-community/whisper-small.en-mlx"
    assert resolve_whisper_repo("someone/custom-whisper") == "someone/custom-whisper"


@pytest.mark.asyncio
async def test_every_mlx_call_runs_on_one_thread(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # MLX aborts the process when weights created on one thread are used on
    # another ("There is no Stream(gpu, 1) in current thread").
    import threading

    thread_ids: dict[str, set[int]] = {"load": set(), "transcribe": set(), "clear": set()}

    class FakeMx:
        float16 = "float16"

        @staticmethod
        def clear_cache() -> None:
            thread_ids["clear"].add(threading.get_ident())

    class FakeModelHolder:
        model = None
        model_path = None

        @classmethod
        def get_model(cls, path: str, dtype: str) -> object:
            thread_ids["load"].add(threading.get_ident())
            cls.model = object()
            return cls.model

    class FakeMlxWhisper:
        @staticmethod
        def transcribe(_path: str, **_kwargs) -> dict:
            thread_ids["transcribe"].add(threading.get_ident())
            return {"segments": [{"start": 0.0, "text": "gamma"}]}

    transcriber = WhisperTranscriber(model_repo="mlx-community/whisper-tiny", idle_unload_seconds=0.05)
    monkeypatch.setattr(transcriber, "_ensure_ffmpeg_available", lambda: None)
    monkeypatch.setattr(transcriber, "_require_mlx_whisper", lambda: (FakeMx, FakeMlxWhisper, FakeModelHolder))

    for _ in range(3):
        assert await transcriber.transcribe(tmp_path / "clip.mp3") == "gamma"
    await asyncio.sleep(0.2)

    assert transcriber.model is None
    all_threads = thread_ids["load"] | thread_ids["transcribe"] | thread_ids["clear"]
    assert len(all_threads) == 1
    assert threading.get_ident() not in all_threads
