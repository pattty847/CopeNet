"""URL download and YouTube caption helpers for media ingest."""

from __future__ import annotations

import asyncio
import html
import os
from pathlib import Path
import re
from typing import Any

from .store import slugify_filename


class MediaDependencyError(RuntimeError):
    """Raised when an optional media dependency is missing."""


class MediaDownloadError(RuntimeError):
    """Raised when download or caption retrieval fails."""


class UniversalDownloader:
    """Small yt-dlp wrapper for CopeNet media imports."""

    YT_COOKIE_BROWSER_ORDER = ("edge", "chrome", "brave", "firefox", "safari")

    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def is_youtube_url(url: str) -> bool:
        lowered = (url or "").lower()
        return "youtube.com" in lowered or "youtu.be" in lowered

    @staticmethod
    def _clean_caption_line(line: str) -> str:
        text = re.sub(r"<[^>]+>", "", line)
        text = html.unescape(text)
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def _normalize_timestamp(raw: str) -> str:
        ts = raw.strip().replace(",", ".")
        parts = ts.split(":")
        if len(parts) == 3:
            hh, mm, ss = parts
            sec = ss.split(".")[0]
            return f"{int(hh):02d}:{int(mm):02d}:{int(sec):02d}"
        if len(parts) == 2:
            mm, ss = parts
            sec = ss.split(".")[0]
            return f"00:{int(mm):02d}:{int(sec):02d}"
        return "00:00:00"

    def parse_caption_text(self, caption_path: Path, *, include_timestamps: bool = True) -> str:
        """Convert subtitle files into readable transcript text."""
        raw = caption_path.read_text(encoding="utf-8", errors="ignore")
        lines = raw.splitlines()
        parsed_lines: list[str] = []
        cue_lines: list[str] = []
        current_timestamp = ""
        last_text = ""

        def flush() -> None:
            nonlocal cue_lines, last_text
            if not cue_lines:
                return
            text = self._clean_caption_line(" ".join(cue_lines))
            cue_lines = []
            if not text or text == last_text:
                return
            last_text = text
            if include_timestamps and current_timestamp:
                parsed_lines.append(f"[{current_timestamp}] {text}")
            else:
                parsed_lines.append(text)

        for line in lines:
            stripped = line.strip()
            if not stripped:
                flush()
                continue
            if stripped.upper().startswith("WEBVTT") or stripped.startswith("Kind:") or stripped.startswith("Language:") or stripped.startswith("NOTE"):
                continue
            if stripped.isdigit():
                continue
            if "-->" in stripped:
                flush()
                current_timestamp = self._normalize_timestamp(stripped.split("-->", 1)[0].strip())
                continue
            cue_lines.append(stripped)

        flush()
        return "\n".join(parsed_lines).strip()

    def _require_yt_dlp(self):
        try:
            import yt_dlp  # type: ignore
        except Exception as exc:  # pragma: no cover - depends on optional install
            raise MediaDependencyError("yt-dlp is required for media URL imports. Install it with `uv sync --extra media`.") from exc
        return yt_dlp

    async def download_youtube_captions(
        self,
        url: str,
        *,
        include_timestamps: bool = True,
    ) -> tuple[str, dict[str, Any]]:
        """Fetch YouTube subtitles and return transcript text plus source metadata."""
        if not self.is_youtube_url(url):
            raise MediaDownloadError("Caption download is only supported for YouTube URLs.")
        yt_dlp = self._require_yt_dlp()
        loop = asyncio.get_running_loop()

        def _run() -> tuple[str, dict[str, Any]]:
            browser_sources = [os.getenv("SUBTEXT_YT_BROWSER", "").strip().lower() or None, *self.YT_COOKIE_BROWSER_ORDER, None]
            browser_sources = list(dict.fromkeys(browser_sources))
            last_error: Exception | None = None
            for browser in browser_sources:
                try:
                    opts: dict[str, Any] = {
                        "skip_download": True,
                        "writesubtitles": True,
                        "writeautomaticsub": True,
                        "subtitlesformat": "vtt/srt/best",
                        "subtitleslangs": ["en", "en-orig", "en-US", "en-GB", "en-.*"],
                        "outtmpl": str(self.output_dir / "%(title).80B [%(id)s].%(ext)s"),
                        "quiet": True,
                        "noprogress": True,
                        "no_warnings": True,
                        "windowsfilenames": True,
                        "restrictfilenames": True,
                        "no_color": True,
                    }
                    if browser:
                        opts["cookiesfrombrowser"] = (browser,)
                    cookies_file = os.getenv("SUBTEXT_YT_COOKIES", "").strip()
                    if cookies_file and Path(cookies_file).exists():
                        opts["cookiefile"] = cookies_file
                    before = {path.resolve() for path in self.output_dir.glob("*")}
                    with yt_dlp.YoutubeDL(opts) as ydl:
                        info = ydl.extract_info(url, download=True)
                    title = str(info.get("title") or info.get("id") or "YouTube Video").strip()
                    video_id = str(info.get("id") or "").strip()
                    candidates = []
                    for path in self.output_dir.glob("*"):
                        if path.resolve() in before:
                            continue
                        if path.suffix.lower() not in {".vtt", ".srt"}:
                            continue
                        if video_id and video_id not in path.name:
                            continue
                        candidates.append(path)
                    if not candidates:
                        raise MediaDownloadError("No subtitle file was produced for this video.")
                    caption_path = max(candidates, key=lambda path: path.stat().st_mtime)
                    text = self.parse_caption_text(caption_path, include_timestamps=include_timestamps)
                    if not text:
                        raise MediaDownloadError("Subtitle file was empty after parsing.")
                    return text, {
                        "title": title,
                        "id": video_id or None,
                        "uploader": info.get("uploader"),
                        "durationSeconds": info.get("duration"),
                        "source": "youtube-captions",
                        "captionPath": str(caption_path),
                    }
                except Exception as exc:
                    last_error = exc
                    continue
            raise MediaDownloadError(str(last_error or "Unable to download YouTube captions."))

        return await loop.run_in_executor(None, _run)

    async def download_best_video(self, url: str) -> tuple[Path, dict[str, Any]]:
        """Download a browser-friendly MP4 video."""
        yt_dlp = self._require_yt_dlp()
        loop = asyncio.get_running_loop()

        def _run() -> tuple[Path, dict[str, Any]]:
            opts = {
                "format": "bestvideo*[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/bestvideo*+bestaudio/best",
                "merge_output_format": "mp4",
                "outtmpl": str(self.output_dir / "%(title).80B [%(id)s].%(ext)s"),
                "quiet": True,
                "noprogress": True,
                "no_warnings": True,
                "windowsfilenames": True,
                "restrictfilenames": True,
                "no_color": True,
            }
            before = {path.resolve() for path in self.output_dir.glob("*")}
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
            title = str(info.get("title") or info.get("id") or "media").strip()
            video_id = str(info.get("id") or "").strip()
            candidates = []
            for path in self.output_dir.glob("*"):
                if path.resolve() in before:
                    continue
                if not path.is_file():
                    continue
                if video_id and video_id not in path.name:
                    continue
                candidates.append(path)
            if not candidates:
                raise MediaDownloadError("No media file was downloaded.")
            media_path = max(candidates, key=lambda path: path.stat().st_mtime)
            return media_path, {
                "title": title,
                "id": video_id or None,
                "uploader": info.get("uploader"),
                "durationSeconds": info.get("duration"),
                "webpageUrl": info.get("webpage_url") or url,
                "source": "yt-dlp",
                "filename": media_path.name,
            }

        return await loop.run_in_executor(None, _run)

    async def copy_local_file(self, source_path: Path) -> tuple[Path, dict[str, Any]]:
        """Copy a local media file into the CopeNet media store."""
        if not source_path.is_file():
            raise MediaDownloadError("Local media path does not exist.")
        target = self.output_dir / f"{slugify_filename(source_path.stem)}-{source_path.stat().st_mtime_ns}{source_path.suffix}"
        loop = asyncio.get_running_loop()

        def _run() -> tuple[Path, dict[str, Any]]:
            target.write_bytes(source_path.read_bytes())
            return target, {
                "title": source_path.stem,
                "source": "local-file",
                "filename": target.name,
            }

        return await loop.run_in_executor(None, _run)
