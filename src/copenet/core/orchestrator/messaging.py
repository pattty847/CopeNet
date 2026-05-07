"""Messaging configuration orchestration helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from copenet.core.messaging import MessagingConfigRecord, TelegramBotConfigRecord
from copenet.core.sessions.session_store import utc_now_iso

if TYPE_CHECKING:
    from . import Orchestrator


def get_messaging_config(orchestrator: "Orchestrator") -> dict[str, Any]:
    """Return the operator-visible messaging configuration."""
    return orchestrator._messaging_store.load().to_public_dict()


def update_messaging_config(
    orchestrator: "Orchestrator",
    *,
    approval_policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Persist a minimal messaging config patch."""
    if not approval_policy:
        return get_messaging_config(orchestrator)

    updated = orchestrator._messaging_store.update_approval_policy(
        require_approval_by_default=approval_policy.get("requireApprovalByDefault"),
        hardline_blocklist=approval_policy.get("hardlineBlocklist"),
    )
    return updated.to_public_dict()


def test_messaging_platform(orchestrator: "Orchestrator", *, platform: str) -> dict[str, Any]:
    """Run a conservative local messaging config test without performing delivery."""
    target_platform = str(platform or "telegram").strip().lower() or "telegram"
    if target_platform != "telegram":
        raise ValueError(f"unsupported messaging platform: {platform}")

    current = orchestrator._messaging_store.load()
    telegram = current.telegram
    if telegram is None or not telegram.token_masked:
        return {
            "platform": "telegram",
            "config": current.to_public_dict(),
            "result": {
                "ok": False,
                "connectionStatus": "unconfigured",
                "message": "No Telegram bot token is configured yet.",
                "verifiedAt": None,
            },
        }

    verified_at = utc_now_iso()
    refreshed = TelegramBotConfigRecord(
        bot_username=telegram.bot_username,
        token_masked=telegram.token_masked,
        connection_status="connected",
        last_verified_at=verified_at,
        error_message=None,
    )
    persisted = orchestrator._messaging_store.update_telegram(refreshed)
    return {
        "platform": "telegram",
        "config": persisted.to_public_dict(),
        "result": {
            "ok": True,
            "connectionStatus": "connected",
            "message": "Telegram bot configuration looks ready.",
            "verifiedAt": verified_at,
        },
    }
