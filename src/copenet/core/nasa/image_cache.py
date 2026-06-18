"""Local cache for NASA APOD image bytes.

apod.nasa.gov (the image host, separate from api.nasa.gov) 503s intermittently, which
shows as a broken Home card. We download each day's image once and serve it from CopeNet
so the card never depends on NASA being up at view time. Dependency-free (stdlib HTTP),
mirroring `core/nasa/service.py`.
"""

from __future__ import annotations

from pathlib import Path
from urllib import error, request

_IMAGE_TIMEOUT = 20.0
_ALLOWED_EXT = (".jpg", ".jpeg", ".png", ".gif", ".webp")


class NasaApodImageCache:
    """Date-keyed on-disk cache of APOD image bytes (one file per day)."""

    def __init__(self, root_dir: Path) -> None:
        self._root = root_dir
        self._root.mkdir(parents=True, exist_ok=True)

    def get(self, date: str) -> Path | None:
        """Return the cached image path for a date, or None if not cached."""
        key = (date or "").strip()
        if not key:
            return None
        for path in sorted(self._root.glob(f"{key}.*")):
            if path.is_file() and not path.name.endswith(".tmp"):
                return path
        return None

    def cache(self, date: str, source_url: str) -> Path | None:
        """Download and persist the image for a date (no-op if already cached).

        Best-effort: returns the path on success, None on any download/IO failure so
        callers can fall back to hotlinking NASA.
        """
        key = (date or "").strip()
        url = (source_url or "").strip()
        if not key or not url:
            return None
        existing = self.get(key)
        if existing is not None:
            return existing
        dest = self._root / f"{key}{_ext_for(url)}"
        try:
            req = request.Request(url, headers={"Accept": "image/*"})
            with request.urlopen(req, timeout=_IMAGE_TIMEOUT) as response:
                body = response.read()
        except (error.URLError, OSError):
            return None
        if not body:
            return None
        tmp = dest.with_suffix(dest.suffix + ".tmp")
        try:
            tmp.write_bytes(body)
            tmp.replace(dest)
        except OSError:
            return None
        return dest


def _ext_for(url: str) -> str:
    lowered = url.lower().split("?", 1)[0]
    for ext in _ALLOWED_EXT:
        if lowered.endswith(ext):
            return ext
    return ".jpg"
