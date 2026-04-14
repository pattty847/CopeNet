"""External app registry and app-local session mapping storage."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import secrets
from pathlib import Path
import threading
from typing import Any


UTC = timezone.utc


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _required_str(raw: dict[str, Any], key: str) -> str:
    value = raw.get(key)
    return str(value).strip() if value is not None else ""


def _optional_str(raw: dict[str, Any], key: str) -> str | None:
    value = raw.get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@dataclass
class AppRegistryEntry:
    app_id: str
    display_name: str
    token_hash: str
    created_at: str
    updated_at: str
    default_provider: str | None = None
    default_model: str | None = None
    allow_tools: bool = False

    @classmethod
    def from_json(cls, raw: dict[str, Any]) -> "AppRegistryEntry":
        now = utc_now_iso()
        return cls(
            app_id=_required_str(raw, "app_id"),
            display_name=_required_str(raw, "display_name") or _required_str(raw, "app_id"),
            token_hash=_required_str(raw, "token_hash"),
            created_at=_required_str(raw, "created_at") or now,
            updated_at=_required_str(raw, "updated_at") or now,
            default_provider=_optional_str(raw, "default_provider"),
            default_model=_optional_str(raw, "default_model"),
            allow_tools=bool(raw.get("allow_tools", False)),
        )

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AppSessionMapping:
    app_id: str
    app_session_id: str
    internal_session_key: str
    created_at: str
    updated_at: str

    @classmethod
    def from_json(cls, raw: dict[str, Any]) -> "AppSessionMapping":
        now = utc_now_iso()
        return cls(
            app_id=_required_str(raw, "app_id"),
            app_session_id=_required_str(raw, "app_session_id"),
            internal_session_key=_required_str(raw, "internal_session_key"),
            created_at=_required_str(raw, "created_at") or now,
            updated_at=_required_str(raw, "updated_at") or now,
        )

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


class AppStore:
    """Thread-safe JSON store for app credentials and external session mappings."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    @property
    def path(self) -> Path:
        return self._path

    def register_app(
        self,
        *,
        app_id: str,
        display_name: str | None = None,
        token: str | None = None,
        default_provider: str | None = None,
        default_model: str | None = None,
        allow_tools: bool = False,
    ) -> tuple[AppRegistryEntry, str]:
        normalized_id = app_id.strip()
        if not normalized_id:
            raise ValueError("app_id is required")
        plain_token = (token or secrets.token_urlsafe(32)).strip()
        if not plain_token:
            raise ValueError("token is required")
        now = utc_now_iso()
        entry = AppRegistryEntry(
            app_id=normalized_id,
            display_name=(display_name or normalized_id).strip() or normalized_id,
            token_hash=hash_token(plain_token),
            created_at=now,
            updated_at=now,
            default_provider=(default_provider or "").strip() or None,
            default_model=(default_model or "").strip() or None,
            allow_tools=allow_tools,
        )
        with self._lock:
            payload = self._load_payload()
            apps = payload["apps"]
            if normalized_id in apps:
                raise ValueError(f"app already exists: {normalized_id}")
            apps[normalized_id] = entry
            self._save_payload(payload)
        return entry, plain_token

    def get_app(self, app_id: str) -> AppRegistryEntry | None:
        with self._lock:
            return self._load_payload()["apps"].get(app_id.strip())

    def authenticate_token(self, token: str) -> AppRegistryEntry | None:
        hashed = hash_token(token.strip())
        if not hashed:
            return None
        with self._lock:
            for entry in self._load_payload()["apps"].values():
                if secrets.compare_digest(entry.token_hash, hashed):
                    return entry
        return None

    def list_mappings_for_app(self, app_id: str) -> list[AppSessionMapping]:
        normalized_id = app_id.strip()
        with self._lock:
            mappings = self._load_payload()["mappings"]
            rows = [mapping for mapping in mappings.values() if mapping.app_id == normalized_id]
        rows.sort(key=lambda row: row.updated_at, reverse=True)
        return rows

    def get_mapping(self, app_id: str, app_session_id: str) -> AppSessionMapping | None:
        normalized_app_id = app_id.strip()
        normalized_session_id = app_session_id.strip()
        with self._lock:
            return self._load_payload()["mappings"].get(f"{normalized_app_id}:{normalized_session_id}")

    def create_mapping(self, *, app_id: str, app_session_id: str, internal_session_key: str) -> AppSessionMapping:
        normalized_app_id = app_id.strip()
        normalized_app_session_id = app_session_id.strip()
        normalized_internal_session_key = internal_session_key.strip()
        if not normalized_app_id:
            raise ValueError("app_id is required")
        if not normalized_app_session_id:
            raise ValueError("app_session_id is required")
        if not normalized_internal_session_key:
            raise ValueError("internal_session_key is required")
        key = f"{normalized_app_id}:{normalized_app_session_id}"
        now = utc_now_iso()
        mapping = AppSessionMapping(
            app_id=normalized_app_id,
            app_session_id=normalized_app_session_id,
            internal_session_key=normalized_internal_session_key,
            created_at=now,
            updated_at=now,
        )
        with self._lock:
            payload = self._load_payload()
            mappings = payload["mappings"]
            existing = mappings.get(key)
            if existing is not None and existing.internal_session_key != normalized_internal_session_key:
                raise ValueError(f"app session already mapped: {normalized_app_session_id}")
            mappings[key] = mapping
            self._save_payload(payload)
        return mapping

    def _load_payload(self) -> dict[str, dict[str, Any]]:
        if not self._path.exists():
            return {"apps": {}, "mappings": {}}
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"apps": {}, "mappings": {}}
        raw_apps = raw.get("apps") if isinstance(raw, dict) else None
        raw_mappings = raw.get("mappings") if isinstance(raw, dict) else None
        apps: dict[str, AppRegistryEntry] = {}
        mappings: dict[str, AppSessionMapping] = {}
        if isinstance(raw_apps, list):
            for item in raw_apps:
                if isinstance(item, dict):
                    entry = AppRegistryEntry.from_json(item)
                    if entry.app_id:
                        apps[entry.app_id] = entry
        if isinstance(raw_mappings, list):
            for item in raw_mappings:
                if isinstance(item, dict):
                    mapping = AppSessionMapping.from_json(item)
                    if mapping.app_id and mapping.app_session_id:
                        mappings[f"{mapping.app_id}:{mapping.app_session_id}"] = mapping
        return {"apps": apps, "mappings": mappings}

    def _save_payload(self, payload: dict[str, dict[str, Any]]) -> None:
        raw = {
            "apps": [entry.to_json() for entry in payload["apps"].values()],
            "mappings": [mapping.to_json() for mapping in payload["mappings"].values()],
        }
        tmp_path = self._path.with_suffix(self._path.suffix + ".tmp")
        tmp_path.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_path.replace(self._path)
