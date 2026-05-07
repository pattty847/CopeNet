"""Durable local-first messaging configuration storage."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import os
from pathlib import Path
import threading
from typing import Any, Literal
from uuid import uuid4

from copenet.core.sessions.session_store import utc_now_iso

PlatformConnectionStatus = Literal["connected", "disconnected", "error", "unconfigured"]


@dataclass(frozen=True)
class MessageDestinationRecord:
    id: str
    platform: str
    target: str
    display_name: str
    thread_label: str | None = None
    is_default: bool = False
    requires_approval: bool = True
    status: str = "configured"

    @classmethod
    def from_json(cls, raw: dict[str, Any]) -> "MessageDestinationRecord":
        return cls(
            id=_required_text(raw, "id"),
            platform=_required_text(raw, "platform") or "telegram",
            target=_required_text(raw, "target"),
            display_name=_required_text(raw, "display_name") or _required_text(raw, "displayName") or _required_text(raw, "target"),
            thread_label=_optional_text(raw, "thread_label") or _optional_text(raw, "threadLabel"),
            is_default=bool(raw.get("is_default", raw.get("isDefault", False))),
            requires_approval=bool(raw.get("requires_approval", raw.get("requiresApproval", True))),
            status=_destination_status(raw.get("status")),
        )

    def to_json(self) -> dict[str, Any]:
        return asdict(self)

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "platform": self.platform,
            "target": self.target,
            "displayName": self.display_name,
            "threadLabel": self.thread_label,
            "isDefault": self.is_default,
            "requiresApproval": self.requires_approval,
            "status": self.status,
        }


@dataclass(frozen=True)
class TelegramBotConfigRecord:
    bot_username: str | None
    token_masked: str | None
    connection_status: PlatformConnectionStatus
    last_verified_at: str | None = None
    error_message: str | None = None

    @classmethod
    def from_json(cls, raw: dict[str, Any] | None) -> "TelegramBotConfigRecord | None":
        if not isinstance(raw, dict):
            return None
        return cls(
            bot_username=_optional_text(raw, "bot_username") or _optional_text(raw, "botUsername"),
            token_masked=_optional_text(raw, "token_masked") or _optional_text(raw, "tokenMasked"),
            connection_status=_connection_status(raw.get("connection_status", raw.get("connectionStatus"))),
            last_verified_at=_optional_text(raw, "last_verified_at") or _optional_text(raw, "lastVerifiedAt"),
            error_message=_optional_text(raw, "error_message") or _optional_text(raw, "errorMessage"),
        )

    def to_json(self) -> dict[str, Any]:
        return asdict(self)

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "botUsername": self.bot_username,
            "tokenMasked": self.token_masked,
            "connectionStatus": self.connection_status,
            "lastVerifiedAt": self.last_verified_at,
            "errorMessage": self.error_message,
        }


@dataclass(frozen=True)
class MessagingApprovalPolicyRecord:
    require_approval_by_default: bool = True
    hardline_blocklist: list[str] = field(default_factory=list)

    @classmethod
    def from_json(cls, raw: dict[str, Any] | None) -> "MessagingApprovalPolicyRecord":
        if not isinstance(raw, dict):
            return cls()
        return cls(
            require_approval_by_default=bool(raw.get("require_approval_by_default", raw.get("requireApprovalByDefault", True))),
            hardline_blocklist=_string_list(raw.get("hardline_blocklist", raw.get("hardlineBlocklist"))),
        )

    def to_json(self) -> dict[str, Any]:
        return asdict(self)

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "requireApprovalByDefault": self.require_approval_by_default,
            "hardlineBlocklist": list(self.hardline_blocklist),
        }


@dataclass(frozen=True)
class MessagingConfigRecord:
    telegram: TelegramBotConfigRecord | None = None
    destinations: list[MessageDestinationRecord] = field(default_factory=list)
    approval_policy: MessagingApprovalPolicyRecord = field(default_factory=MessagingApprovalPolicyRecord)

    @classmethod
    def from_json(cls, raw: dict[str, Any]) -> "MessagingConfigRecord":
        return cls(
            telegram=TelegramBotConfigRecord.from_json(raw.get("telegram")),
            destinations=_destinations_list(raw.get("destinations")),
            approval_policy=MessagingApprovalPolicyRecord.from_json(raw.get("approval_policy", raw.get("approvalPolicy"))),
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "telegram": self.telegram.to_json() if self.telegram is not None else None,
            "destinations": [item.to_json() for item in self.destinations],
            "approval_policy": self.approval_policy.to_json(),
        }

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "telegram": self.telegram.to_public_dict() if self.telegram is not None else None,
            "destinations": [item.to_public_dict() for item in self.destinations],
            "approvalPolicy": self.approval_policy.to_public_dict(),
        }


class MessagingConfigStore:
    """Thread-safe JSON store for messaging config and destinations."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def load(self) -> MessagingConfigRecord:
        with self._lock:
            return self._load_unlocked()

    def save(self, record: MessagingConfigRecord) -> MessagingConfigRecord:
        persisted = _refresh_record(record)
        with self._lock:
            self._save_unlocked(persisted)
        return persisted

    def update_approval_policy(
        self,
        *,
        require_approval_by_default: bool | None = None,
        hardline_blocklist: list[str] | None = None,
    ) -> MessagingConfigRecord:
        with self._lock:
            current = self._load_unlocked()
            policy = MessagingApprovalPolicyRecord(
                require_approval_by_default=current.approval_policy.require_approval_by_default
                if require_approval_by_default is None
                else bool(require_approval_by_default),
                hardline_blocklist=current.approval_policy.hardline_blocklist
                if hardline_blocklist is None
                else _string_list(hardline_blocklist),
            )
            updated = _refresh_record(
                MessagingConfigRecord(
                    telegram=current.telegram,
                    destinations=current.destinations,
                    approval_policy=policy,
                )
            )
            self._save_unlocked(updated)
        return updated

    def update_telegram(self, telegram: TelegramBotConfigRecord | None) -> MessagingConfigRecord:
        with self._lock:
            current = self._load_unlocked()
            updated = _refresh_record(
                MessagingConfigRecord(
                    telegram=telegram,
                    destinations=current.destinations,
                    approval_policy=current.approval_policy,
                )
            )
            self._save_unlocked(updated)
        return updated

    def upsert_destination(self, destination: MessageDestinationRecord) -> MessagingConfigRecord:
        with self._lock:
            current = self._load_unlocked()
            normalized = MessageDestinationRecord(
                id=destination.id.strip() or f"dest-{uuid4()}",
                platform=destination.platform.strip() or "telegram",
                target=destination.target.strip(),
                display_name=destination.display_name.strip() or destination.target.strip(),
                thread_label=destination.thread_label.strip() if destination.thread_label else None,
                is_default=bool(destination.is_default),
                requires_approval=bool(destination.requires_approval),
                status=_destination_status(destination.status),
            )
            rows: list[MessageDestinationRecord] = []
            replaced = False
            for item in current.destinations:
                if item.id == normalized.id:
                    rows.append(normalized)
                    replaced = True
                elif normalized.is_default and item.platform == normalized.platform:
                    rows.append(
                        MessageDestinationRecord(
                            id=item.id,
                            platform=item.platform,
                            target=item.target,
                            display_name=item.display_name,
                            thread_label=item.thread_label,
                            is_default=False,
                            requires_approval=item.requires_approval,
                            status=item.status,
                        )
                    )
                else:
                    rows.append(item)
            if not replaced:
                if normalized.is_default:
                    rows = [
                        MessageDestinationRecord(
                            id=item.id,
                            platform=item.platform,
                            target=item.target,
                            display_name=item.display_name,
                            thread_label=item.thread_label,
                            is_default=False if item.platform == normalized.platform else item.is_default,
                            requires_approval=item.requires_approval,
                            status=item.status,
                        )
                        for item in rows
                    ]
                rows.append(normalized)
            updated = _refresh_record(
                MessagingConfigRecord(
                    telegram=current.telegram,
                    destinations=rows,
                    approval_policy=current.approval_policy,
                )
            )
            self._save_unlocked(updated)
        return updated

    def delete_destination(self, destination_id: str) -> MessagingConfigRecord:
        target_id = destination_id.strip()
        with self._lock:
            current = self._load_unlocked()
            updated = _refresh_record(
                MessagingConfigRecord(
                    telegram=current.telegram,
                    destinations=[item for item in current.destinations if item.id != target_id],
                    approval_policy=current.approval_policy,
                )
            )
            self._save_unlocked(updated)
        return updated

    def _load_unlocked(self) -> MessagingConfigRecord:
        if not self._path.exists():
            return _default_record_from_env()
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return _default_record_from_env()
        if not isinstance(raw, dict):
            return _default_record_from_env()
        config = raw.get("config") if isinstance(raw.get("config"), dict) else raw
        if not isinstance(config, dict):
            return _default_record_from_env()
        return _refresh_record(MessagingConfigRecord.from_json(config))

    def _save_unlocked(self, record: MessagingConfigRecord) -> None:
        payload = {"config": record.to_json(), "updated_at": utc_now_iso()}
        tmp_path = self._path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_path.replace(self._path)


def _default_record_from_env() -> MessagingConfigRecord:
    telegram = _telegram_from_env()
    destinations = _destinations_from_env()
    policy = MessagingApprovalPolicyRecord(
        require_approval_by_default=_env_bool("COPNET_MESSAGING_REQUIRE_APPROVAL_BY_DEFAULT", True),
        hardline_blocklist=_csv_list(os.environ.get("COPNET_MESSAGING_HARDLINE_BLOCKLIST", "")),
    )
    return _refresh_record(MessagingConfigRecord(telegram=telegram, destinations=destinations, approval_policy=policy))


def _telegram_from_env() -> TelegramBotConfigRecord | None:
    token = os.environ.get("COPNET_TELEGRAM_BOT_TOKEN", "").strip()
    username = os.environ.get("COPNET_TELEGRAM_BOT_USERNAME", "").strip() or None
    if not token and not username:
        return None
    return TelegramBotConfigRecord(
        bot_username=username,
        token_masked=_mask_token(token) if token else None,
        connection_status="disconnected" if token else "unconfigured",
        last_verified_at=None,
        error_message=None,
    )


def _destinations_from_env() -> list[MessageDestinationRecord]:
    raw_json = os.environ.get("COPNET_MESSAGING_DESTINATIONS_JSON", "").strip()
    if raw_json:
        try:
            parsed = json.loads(raw_json)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, list):
            rows = _destinations_list(parsed)
            if rows:
                return rows

    default_target = os.environ.get("COPNET_TELEGRAM_DEFAULT_TARGET", "").strip()
    if not default_target:
        return []
    return [
        MessageDestinationRecord(
            id=os.environ.get("COPNET_TELEGRAM_DEFAULT_DESTINATION_ID", "telegram-default").strip() or "telegram-default",
            platform="telegram",
            target=default_target,
            display_name=os.environ.get("COPNET_TELEGRAM_DEFAULT_DISPLAY_NAME", default_target).strip() or default_target,
            thread_label=os.environ.get("COPNET_TELEGRAM_DEFAULT_THREAD_LABEL", "").strip() or None,
            is_default=True,
            requires_approval=_env_bool("COPNET_TELEGRAM_DEFAULT_REQUIRES_APPROVAL", True),
            status="configured",
        )
    ]


def _mask_token(token: str) -> str | None:
    cleaned = token.strip()
    if not cleaned:
        return None
    if len(cleaned) <= 8:
        return f"tg:{cleaned}"
    return f"tg:{cleaned[:4]}...{cleaned[-4:]}"


def _required_text(raw: dict[str, Any], key: str) -> str:
    value = raw.get(key)
    return str(value).strip() if value is not None else ""


def _optional_text(raw: dict[str, Any], key: str) -> str | None:
    value = raw.get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _string_list(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    rows: list[str] = []
    for item in raw:
        text = str(item or "").strip()
        if text:
            rows.append(text)
    return rows


def _csv_list(raw: str) -> list[str]:
    return [token.strip() for token in raw.split(",") if token.strip()]


def _destinations_list(raw: Any) -> list[MessageDestinationRecord]:
    if not isinstance(raw, list):
        return []
    rows: list[MessageDestinationRecord] = []
    seen_ids: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        record = MessageDestinationRecord.from_json(item)
        if not record.id or not record.target or record.id in seen_ids:
            continue
        rows.append(record)
        seen_ids.add(record.id)
    return rows


def _destination_status(value: Any) -> str:
    text = str(value or "configured").strip().lower()
    if text in {"configured", "unconfigured", "error"}:
        return text
    return "configured"


def _connection_status(value: Any) -> PlatformConnectionStatus:
    text = str(value or "unconfigured").strip().lower()
    if text in {"connected", "disconnected", "error"}:
        return text
    return "unconfigured"


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _refresh_record(record: MessagingConfigRecord) -> MessagingConfigRecord:
    return MessagingConfigRecord(
        telegram=record.telegram,
        destinations=[
            MessageDestinationRecord(
                id=item.id.strip(),
                platform=item.platform.strip() or "telegram",
                target=item.target.strip(),
                display_name=item.display_name.strip() or item.target.strip(),
                thread_label=item.thread_label.strip() if item.thread_label else None,
                is_default=bool(item.is_default),
                requires_approval=bool(item.requires_approval),
                status=_destination_status(item.status),
            )
            for item in record.destinations
            if item.id.strip() and item.target.strip()
        ],
        approval_policy=MessagingApprovalPolicyRecord(
            require_approval_by_default=bool(record.approval_policy.require_approval_by_default),
            hardline_blocklist=_string_list(record.approval_policy.hardline_blocklist),
        ),
    )
