from __future__ import annotations

from pathlib import Path

import pytest

from copenet.core.nasa import NasaApodRecord, NasaApodStore
from copenet.core.nasa.wallpaper import (
    apply_apod_wallpaper,
    _default_agent_program_arguments,
    install_launch_agent,
    set_macos_wallpaper,
)


class FakeApodService:
    def __init__(self, payload: dict | None = None, error: Exception | None = None, configured: bool = True) -> None:
        self.payload = payload
        self.error = error
        self.configured = configured
        self.calls: list[dict[str, object]] = []

    def fetch(self, *, date: str | None = None) -> dict:
        self.calls.append({"date": date})
        if self.error:
            raise self.error
        assert self.payload is not None
        return dict(self.payload)


class FakeImageCache:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.cached: list[tuple[str, str]] = []

    def cache(self, date: str, source_url: str) -> Path | None:
        self.cached.append((date, source_url))
        if not source_url:
            return None
        path = self.root / f"{date}.jpg"
        path.write_bytes(b"image")
        return path


def _image_payload(date: str, title: str = "Deep field") -> dict:
    return {
        "date": date,
        "title": title,
        "explanation": "Stars on stars.",
        "url": f"https://example.test/{date}.jpg",
        "hdurl": None,
        "thumbnail_url": None,
        "media_type": "image",
    }


def _video_payload(date: str) -> dict:
    return {
        "date": date,
        "title": "Space video",
        "explanation": "A video APOD.",
        "url": f"https://example.test/{date}.mp4",
        "hdurl": None,
        "thumbnail_url": "https://example.test/thumb.jpg",
        "media_type": "video",
    }


def test_apply_apod_wallpaper_fetches_caches_and_applies_today_image(tmp_path: Path) -> None:
    applied: list[Path] = []
    store = NasaApodStore(tmp_path / "nasa-apod.json")
    cache = FakeImageCache(tmp_path / "images")

    result = apply_apod_wallpaper(
        service=FakeApodService(_image_payload("2026-06-29", "Today image")),
        store=store,
        image_cache=cache,
        set_wallpaper=applied.append,
        platform="darwin",
    )

    assert result.ok is True
    assert result.status == "applied"
    assert result.date == "2026-06-29"
    assert result.title == "Today image"
    assert result.image_path == str(tmp_path / "images" / "2026-06-29.jpg")
    assert applied == [tmp_path / "images" / "2026-06-29.jpg"]
    assert cache.cached == [("2026-06-29", "https://example.test/2026-06-29.jpg")]


def test_apply_apod_wallpaper_uses_previous_image_when_today_is_video(tmp_path: Path) -> None:
    applied: list[Path] = []
    store = NasaApodStore(tmp_path / "nasa-apod.json")
    store.save(NasaApodRecord.from_json(_image_payload("2026-06-28", "Yesterday image")))
    cache = FakeImageCache(tmp_path / "images")

    result = apply_apod_wallpaper(
        service=FakeApodService(_video_payload("2026-06-29")),
        store=store,
        image_cache=cache,
        set_wallpaper=applied.append,
        platform="darwin",
    )

    assert result.ok is True
    assert result.status == "fallback_applied"
    assert result.reason == "today_apod_is_video"
    assert result.date == "2026-06-28"
    assert result.title == "Yesterday image"
    assert applied == [tmp_path / "images" / "2026-06-28.jpg"]


def test_apply_apod_wallpaper_skips_video_when_no_previous_image(tmp_path: Path) -> None:
    applied: list[Path] = []

    result = apply_apod_wallpaper(
        service=FakeApodService(_video_payload("2026-06-29")),
        store=NasaApodStore(tmp_path / "nasa-apod.json"),
        image_cache=FakeImageCache(tmp_path / "images"),
        set_wallpaper=applied.append,
        platform="darwin",
    )

    assert result.ok is False
    assert result.status == "skipped"
    assert result.reason == "today_apod_is_video_no_previous_image"
    assert result.error is None
    assert applied == []


def test_apply_apod_wallpaper_fetch_failure_keeps_existing_wallpaper(tmp_path: Path) -> None:
    applied: list[Path] = []

    result = apply_apod_wallpaper(
        service=FakeApodService(error=RuntimeError("NASA APOD HTTP 404")),
        store=NasaApodStore(tmp_path / "nasa-apod.json"),
        image_cache=FakeImageCache(tmp_path / "images"),
        set_wallpaper=applied.append,
        platform="darwin",
    )

    assert result.ok is False
    assert result.status == "skipped"
    assert result.reason == "nasa_apod_unavailable"
    assert result.error == "NASA APOD HTTP 404"
    assert applied == []


def test_apply_apod_wallpaper_rejects_non_macos_before_fetching(tmp_path: Path) -> None:
    service = FakeApodService(_image_payload("2026-06-29"))

    result = apply_apod_wallpaper(
        service=service,
        store=NasaApodStore(tmp_path / "nasa-apod.json"),
        image_cache=FakeImageCache(tmp_path / "images"),
        platform="linux",
    )

    assert result.ok is False
    assert result.status == "error"
    assert result.reason == "unsupported_platform"
    assert result.error == "unsupported platform: macOS required"
    assert service.calls == []


def test_set_macos_wallpaper_uses_automator_desktop_picture_workflow(tmp_path: Path) -> None:
    image = tmp_path / "space.jpg"
    image.write_bytes(b"image")
    commands: list[list[str]] = []

    set_macos_wallpaper(image, platform="darwin", run_command=lambda command: commands.append(command))

    assert commands == [
        [
            "automator",
            "-i",
            str(image.resolve()),
            "/System/Library/Services/Set Desktop Picture.workflow",
        ]
    ]


def test_set_macos_wallpaper_rejects_non_macos(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="unsupported platform"):
        set_macos_wallpaper(tmp_path / "space.jpg", platform="linux", run_command=lambda _: None)


def test_install_launch_agent_writes_expected_schedule_and_command(tmp_path: Path) -> None:
    loaded: list[Path] = []

    plist = install_launch_agent(
        launch_agents_dir=tmp_path / "LaunchAgents",
        logs_dir=tmp_path / "logs",
        program_arguments=["/usr/bin/env", "uv", "run", "copenet", "nasa", "wallpaper", "apply"],
        load_agent=loaded.append,
    )

    text = plist.read_text(encoding="utf-8")
    assert plist == tmp_path / "LaunchAgents" / "com.copenet.nasa-wallpaper.plist"
    assert "<integer>3</integer>" in text
    assert "<integer>6</integer>" in text
    assert "<integer>9</integer>" in text
    assert "nasa-wallpaper.out.log" in text
    assert "<string>copenet</string>" in text
    assert loaded == [plist]


def test_launch_agent_status_reports_file_and_loaded_state(tmp_path: Path) -> None:
    launch_agents = tmp_path / "LaunchAgents"
    launch_agents.mkdir()
    plist = launch_agents / "com.copenet.nasa-wallpaper.plist"
    plist.write_text("plist", encoding="utf-8")

    from copenet.core.nasa.wallpaper import launch_agent_status

    status = launch_agent_status(launch_agents_dir=launch_agents, is_loaded=lambda path: path == plist)

    assert status == {"installed": True, "loaded": True, "path": str(plist)}


def test_default_launch_agent_command_uses_resolved_uv_path(monkeypatch) -> None:
    monkeypatch.setattr("copenet.core.nasa.wallpaper.shutil.which", lambda name: "/opt/homebrew/bin/uv" if name == "uv" else None)

    args = _default_agent_program_arguments()

    assert args[:3] == ["/opt/homebrew/bin/uv", "run", "copenet"]
