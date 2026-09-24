from __future__ import annotations

from pathlib import Path

import pytest

from copenet.core.media import MediaAssetStore, MediaIngestionService, UniversalDownloader, render_transcript_attachment
from copenet.core.media.timestamps import format_timestamp, strip_timestamps, timestamped_line


def test_timestamps_render_as_hours_minutes_seconds() -> None:
    assert format_timestamp(0) == "00:00:00"
    assert format_timestamp(65.9) == "00:01:05"
    assert format_timestamp(3725) == "01:02:05"


def test_caption_and_whisper_transcripts_share_one_line_format(tmp_path: Path) -> None:
    vtt = tmp_path / "clip.en.vtt"
    vtt.write_text("WEBVTT\n\n00:05:07.200 --> 00:05:09.000\nNow it is night.\n", encoding="utf-8")

    caption_text = UniversalDownloader(tmp_path).parse_caption_text(vtt)

    assert caption_text == timestamped_line(307.2, "Now it is night.") == "[00:05:07] Now it is night."


def test_discussed_transcript_explains_its_timestamps_only_when_it_has_them() -> None:
    _, stamped = render_transcript_attachment({"title": "Clip", "transcriptContent": "[00:00:12] Day.\n[00:05:07] Night."})
    _, plain = render_transcript_attachment({"title": "Clip", "transcriptContent": "Day. Night."})

    assert "Timestamps: each line starts with [HH:MM:SS]" in stamped
    assert "Timestamps:" not in plain


def test_asset_card_excerpt_reads_as_prose() -> None:
    assert strip_timestamps("[00:00:12] Day.\n[00:05:07] Night.") == "Day.\nNight."


class _FakeDownloader:
    def __init__(self, media_path: Path) -> None:
        self.media_path = media_path

    async def copy_local_file(self, source_path: Path):
        return self.media_path, {"title": "Day and night"}


class _FakeTranscriber:
    def __init__(self) -> None:
        self.calls: list[bool] = []

    async def transcribe(self, audio_path: Path, *, include_timestamps: bool = False) -> str:
        self.calls.append(include_timestamps)
        return "[00:00:12] It is day out.\n[00:05:07] Now it is night." if include_timestamps else "It is day out. Now it is night."

    def get_audio_duration(self, audio_path: Path) -> float:
        return 320.0


@pytest.mark.asyncio
async def test_uploaded_media_is_imported_with_timestamps(tmp_path: Path) -> None:
    media_path = tmp_path / "clip.m4a"
    media_path.write_bytes(b"audio")
    transcriber = _FakeTranscriber()
    service = MediaIngestionService(
        store=MediaAssetStore(tmp_path / "media"),
        downloader=_FakeDownloader(media_path),
        transcriber=transcriber,
    )

    record = await service.import_local_file(app_id="copenet-web", source_path=media_path)
    detail = service.get_asset_detail(app_id="copenet-web", asset_id=record.asset_id)

    assert transcriber.calls == [True]
    assert detail["transcriptContent"].startswith("[00:00:12] It is day out.")
    assert record.transcript_excerpt == "It is day out. Now it is night."
