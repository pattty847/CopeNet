from __future__ import annotations

from pathlib import Path

import pytest

from copenet.core.media.transcriber import WhisperTranscriber


class _FakeModel:
    def __init__(self, *, text: str) -> None:
        self._text = text

    def transcribe(self, _path: str, fp16: bool = False) -> dict[str, object]:
        return {"text": self._text, "segments": [{"text": self._text}]}


@pytest.mark.asyncio
async def test_transcribe_stream_unloads_model_after_success(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    transcriber = WhisperTranscriber(model_name="tiny")
    monkeypatch.setattr(transcriber, "_ensure_ffmpeg_available", lambda: None)

    load_calls = 0
    unload_calls = 0

    async def fake_load_model() -> None:
        nonlocal load_calls
        load_calls += 1
        transcriber.model = _FakeModel(text="alpha")

    def fake_unload_model() -> None:
        nonlocal unload_calls
        unload_calls += 1
        transcriber.model = None

    monkeypatch.setattr(transcriber, "load_model", fake_load_model)
    monkeypatch.setattr(transcriber, "unload_model", fake_unload_model)

    chunks: list[str] = []
    async for chunk in transcriber.transcribe_stream(tmp_path / "clip.mp3"):
        chunks.append(chunk)

    assert chunks == ["alpha"]
    assert load_calls == 1
    assert unload_calls == 1
    assert transcriber.model is None


@pytest.mark.asyncio
async def test_progress_stream_unloads_model_after_completion(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    transcriber = WhisperTranscriber(model_name="tiny")
    monkeypatch.setattr(transcriber, "_ensure_ffmpeg_available", lambda: None)
    monkeypatch.setattr(transcriber, "get_audio_duration", lambda _path: 0.0)

    load_calls = 0
    unload_calls = 0

    async def fake_load_model() -> None:
        nonlocal load_calls
        load_calls += 1
        transcriber.model = _FakeModel(text="beta")

    def fake_unload_model() -> None:
        nonlocal unload_calls
        unload_calls += 1
        transcriber.model = None

    monkeypatch.setattr(transcriber, "load_model", fake_load_model)
    monkeypatch.setattr(transcriber, "unload_model", fake_unload_model)

    events: list[dict[str, object]] = []
    async for event in transcriber.progress_stream(tmp_path / "clip.mp3"):
        events.append(event)

    assert [event["type"] for event in events] == ["progress", "progress", "chunk", "progress"]
    assert load_calls == 2
    assert unload_calls == 1
    assert transcriber.model is None
