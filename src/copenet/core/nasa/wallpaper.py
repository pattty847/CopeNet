"""Headless NASA APOD wallpaper support.

This module intentionally does not depend on the CopeNet host/UI. It reuses the
same APOD service, JSON store, and image cache so a LaunchAgent can refresh the
desktop wallpaper while CopeNet is closed.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import plistlib
import subprocess
import sys
from typing import Any, Callable, Sequence

from copenet._paths import default_sessions_dir
from copenet.core.nasa.image_cache import NasaApodImageCache
from copenet.core.nasa.service import NasaApodError, NasaApodService
from copenet.core.nasa.store import NasaApodRecord, NasaApodStore


WALLPAPER_AGENT_LABEL = "com.copenet.nasa-wallpaper"
WALLPAPER_AGENT_FILENAME = f"{WALLPAPER_AGENT_LABEL}.plist"
WALLPAPER_RETRY_HOURS = (3, 6, 9)


@dataclass(frozen=True)
class WallpaperResult:
    ok: bool
    status: str
    date: str | None = None
    title: str | None = None
    image_path: str | None = None
    reason: str | None = None
    error: str | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "status": self.status,
            "date": self.date,
            "title": self.title,
            "imagePath": self.image_path,
            "reason": self.reason,
            "error": self.error,
        }


def apply_apod_wallpaper(
    *,
    date: str | None = None,
    refresh: bool = False,
    service: NasaApodService | None = None,
    store: NasaApodStore | None = None,
    image_cache: NasaApodImageCache | None = None,
    set_wallpaper: Callable[[Path], None] | None = None,
    platform: str | None = None,
) -> WallpaperResult:
    """Fetch/cache APOD and apply an image wallpaper.

    Video APODs are persisted for history, but v1 wallpaper uses the newest
    previous image APOD instead of thumbnails.
    """
    base = default_sessions_dir()
    service = service or NasaApodService()
    store = store or NasaApodStore(path=base / "nasa-apod.json")
    image_cache = image_cache or NasaApodImageCache(root_dir=base / "nasa-apod-images")

    actual_platform = platform or sys.platform
    if set_wallpaper is None and actual_platform != "darwin":
        return WallpaperResult(ok=False, status="error", reason="unsupported_platform", error="unsupported platform: macOS required")
    set_wallpaper = set_wallpaper or (lambda path: set_macos_wallpaper(path, platform=platform))
    if not getattr(service, "configured", True):
        return WallpaperResult(ok=False, status="error", reason="missing_api_key", error="NASA_API_KEY is not set")

    try:
        fetched = service.fetch(date=date)
    except (NasaApodError, RuntimeError, OSError) as exc:
        return WallpaperResult(ok=False, status="skipped", reason="nasa_apod_unavailable", error=str(exc))

    record = store.save(NasaApodRecord.from_json(fetched))
    if record.media_type == "video":
        previous = _newest_cached_image_record(store, exclude_date=record.date)
        if previous is None:
            return WallpaperResult(ok=False, status="skipped", reason="today_apod_is_video_no_previous_image")
        return _cache_and_apply(
            previous,
            image_cache=image_cache,
            set_wallpaper=set_wallpaper,
            status="fallback_applied",
            reason="today_apod_is_video",
        )

    return _cache_and_apply(record, image_cache=image_cache, set_wallpaper=set_wallpaper, status="applied")


def set_macos_wallpaper(
    image_path: Path,
    *,
    platform: str | None = None,
    run_command: Callable[[list[str]], Any] | None = None,
) -> None:
    """Set an image as the macOS wallpaper for every desktop."""
    actual_platform = platform or sys.platform
    if actual_platform != "darwin":
        raise RuntimeError("unsupported platform: macOS required")
    path = image_path.expanduser().resolve()
    if not path.is_file():
        raise RuntimeError(f"wallpaper image does not exist: {path}")
    script = f'tell application "System Events" to set picture of every desktop to POSIX file {_applescript_string(str(path))}'
    command = ["osascript", "-e", script]
    if run_command is not None:
        run_command(command)
        return
    completed = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False)
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        raise RuntimeError(f"failed to apply macOS wallpaper{f': {detail}' if detail else ''}")


def install_launch_agent(
    *,
    launch_agents_dir: Path | None = None,
    logs_dir: Path | None = None,
    program_arguments: Sequence[str] | None = None,
    working_directory: Path | None = None,
) -> Path:
    """Write the LaunchAgent plist that refreshes APOD wallpaper in the morning."""
    launch_agents_dir = launch_agents_dir or (Path.home() / "Library" / "LaunchAgents")
    logs_dir = logs_dir or (Path.home() / ".copenet" / "logs")
    program_arguments = list(program_arguments or _default_agent_program_arguments())
    launch_agents_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    plist_path = launch_agents_dir / WALLPAPER_AGENT_FILENAME
    payload: dict[str, Any] = {
        "Label": WALLPAPER_AGENT_LABEL,
        "ProgramArguments": program_arguments,
        "StartCalendarInterval": [{"Hour": hour, "Minute": 0} for hour in WALLPAPER_RETRY_HOURS],
        "StandardOutPath": str(logs_dir / "nasa-wallpaper.out.log"),
        "StandardErrorPath": str(logs_dir / "nasa-wallpaper.err.log"),
    }
    if working_directory is not None:
        payload["WorkingDirectory"] = str(working_directory.expanduser().resolve())
    with plist_path.open("wb") as handle:
        plistlib.dump(payload, handle, sort_keys=False)
    return plist_path


def uninstall_launch_agent(*, launch_agents_dir: Path | None = None) -> Path:
    launch_agents_dir = launch_agents_dir or (Path.home() / "Library" / "LaunchAgents")
    plist_path = launch_agents_dir / WALLPAPER_AGENT_FILENAME
    try:
        plist_path.unlink()
    except FileNotFoundError:
        pass
    return plist_path


def launch_agent_status(*, launch_agents_dir: Path | None = None) -> dict[str, Any]:
    launch_agents_dir = launch_agents_dir or (Path.home() / "Library" / "LaunchAgents")
    plist_path = launch_agents_dir / WALLPAPER_AGENT_FILENAME
    return {"installed": plist_path.is_file(), "path": str(plist_path)}


def _cache_and_apply(
    record: NasaApodRecord,
    *,
    image_cache: NasaApodImageCache,
    set_wallpaper: Callable[[Path], None],
    status: str,
    reason: str | None = None,
) -> WallpaperResult:
    image_path = image_cache.cache(record.date, record.url or record.hdurl or "")
    if image_path is None:
        return WallpaperResult(ok=False, status="skipped", date=record.date, title=record.title, reason="image_cache_unavailable")
    try:
        set_wallpaper(image_path)
    except Exception as exc:
        return WallpaperResult(
            ok=False,
            status="error",
            date=record.date,
            title=record.title,
            image_path=str(image_path),
            reason="wallpaper_apply_failed",
            error=str(exc),
        )
    return WallpaperResult(
        ok=True,
        status=status,
        date=record.date,
        title=record.title,
        image_path=str(image_path),
        reason=reason,
    )


def _newest_cached_image_record(store: NasaApodStore, *, exclude_date: str) -> NasaApodRecord | None:
    for record in store.list(limit=None):
        if record.date != exclude_date and record.media_type == "image":
            return record
    return None


def _default_agent_program_arguments() -> list[str]:
    return ["/usr/bin/env", "uv", "run", "copenet", "nasa", "wallpaper", "apply", "--json"]


def _applescript_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
