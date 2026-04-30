from __future__ import annotations

import json
import os
import secrets
import tempfile
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterator


@dataclass(frozen=True)
class ProviderAuthProfile:
    provider: str
    profile_id: str
    access_token: str
    refresh_token: str
    expires_at: int
    account_id: str | None = None
    scopes: tuple[str, ...] = ()
    updated_at: str | None = None

    def to_public_dict(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "profileId": self.profile_id,
            "expiresAt": self.expires_at,
            "accountId": self.account_id,
            "scopes": list(self.scopes),
            "updatedAt": self.updated_at,
        }


class ProviderAuthStore:
    """Small JSON-backed provider auth store with an advisory lock file."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock_path = path.with_name(f"{path.name}.lock")

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> ProviderAuthProfile | None:
        if not self._path.exists():
            return None
        raw = json.loads(self._path.read_text("utf-8"))
        if not isinstance(raw, dict):
            raise RuntimeError("provider auth store is invalid")
        profile = raw.get("profile")
        if not isinstance(profile, dict):
            return None
        return ProviderAuthProfile(
            provider=str(profile.get("provider") or "").strip(),
            profile_id=str(profile.get("profile_id") or "default").strip() or "default",
            access_token=str(profile.get("access_token") or "").strip(),
            refresh_token=str(profile.get("refresh_token") or "").strip(),
            expires_at=int(profile.get("expires_at") or 0),
            account_id=str(profile.get("account_id") or "").strip() or None,
            scopes=tuple(_normalize_scopes(profile.get("scopes"))),
            updated_at=str(profile.get("updated_at") or "").strip() or None,
        )

    def save(self, profile: ProviderAuthProfile) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": 1, "profile": asdict(profile)}
        fd, temp_path = tempfile.mkstemp(prefix=f".{self._path.name}.", dir=str(self._path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, sort_keys=True)
                handle.write("\n")
            os.replace(temp_path, self._path)
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    def clear(self) -> None:
        if self._path.exists():
            self._path.unlink()

    @contextmanager
    def locked(self, timeout_sec: float = 10.0, poll_sec: float = 0.05) -> Iterator[None]:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + timeout_sec
        token = secrets.token_hex(8)
        while True:
            try:
                fd = os.open(self._lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    handle.write(token)
                break
            except FileExistsError:
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"provider auth store lock timed out: {self._lock_path}")
                time.sleep(poll_sec)
        try:
            yield
        finally:
            try:
                if self._lock_path.exists():
                    self._lock_path.unlink()
            except FileNotFoundError:
                pass


def _normalize_scopes(value: object) -> list[str]:
    if isinstance(value, str):
        return [token for token in value.split() if token]
    if isinstance(value, list):
        normalized: list[str] = []
        for item in value:
            text = str(item or "").strip()
            if text:
                normalized.append(text)
        return normalized
    return []
