"""Messaging configuration and Telegram routing orchestration helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from copenet.core.messaging import (
    MessageDestinationRecord,
    MessagingConfigRecord,
    TelegramBotConfigRecord,
    TelegramDefaultsRecord,
    TelegramSessionRouteRecord,
)
from copenet.core.orchestrator.catalog import create_session_with_profile, session_payload
from copenet.core.sessions.session_store import utc_now_iso

if TYPE_CHECKING:
    from . import Orchestrator


def get_messaging_config(orchestrator: "Orchestrator") -> dict[str, Any]:
    """Return the operator-visible messaging configuration."""
    payload = orchestrator._messaging_store.load().to_public_dict()
    payload["routes"] = list_messaging_routes(orchestrator)
    return payload


def update_messaging_config(
    orchestrator: "Orchestrator",
    *,
    approval_policy: dict[str, Any] | None = None,
    telegram_defaults: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Persist a minimal messaging config patch."""
    current = orchestrator._messaging_store.load()
    updated = current
    if approval_policy:
        updated = orchestrator._messaging_store.update_approval_policy(
            require_approval_by_default=approval_policy.get("requireApprovalByDefault"),
            hardline_blocklist=approval_policy.get("hardlineBlocklist"),
        )
    if telegram_defaults is not None:
        updated = orchestrator._messaging_store.update_telegram_defaults(
            TelegramDefaultsRecord.from_json(telegram_defaults)
        )
    if not approval_policy and telegram_defaults is None:
        return get_messaging_config(orchestrator)

    return get_messaging_config(orchestrator)


def list_messaging_destinations(orchestrator: "Orchestrator") -> list[dict[str, Any]]:
    """Return the configured operator messaging destinations."""
    return [item.to_public_dict() for item in orchestrator._messaging_store.load().destinations]


def list_messaging_routes(orchestrator: "Orchestrator") -> list[dict[str, Any]]:
    """Return Telegram chat/thread routes mapped to CopeNet sessions."""
    return [item.to_public_dict() for item in orchestrator._route_store.list_routes()]


def upsert_messaging_destination(
    orchestrator: "Orchestrator",
    *,
    destination: dict[str, Any],
) -> dict[str, Any]:
    """Create or update one messaging destination."""
    record = MessageDestinationRecord.from_json(destination)
    if not record.target:
      raise ValueError("destination target is required")
    if not record.display_name:
      raise ValueError("destination displayName is required")
    updated = orchestrator._messaging_store.upsert_destination(record)
    target = next((item for item in updated.destinations if item.target == record.target and item.platform == record.platform), None)
    return {
        "destination": target.to_public_dict() if target is not None else None,
        "config": get_messaging_config(orchestrator),
    }


def upsert_messaging_route(orchestrator: "Orchestrator", *, route: dict[str, Any]) -> dict[str, Any]:
    """Create or update one Telegram chat/thread route."""
    record = TelegramSessionRouteRecord.from_json(route)
    if not record.chat_id:
        raise ValueError("route chatId is required")
    if not record.session_key:
        raise ValueError("route sessionKey is required")
    rows = orchestrator._route_store.upsert_route(record)
    target = next(
        (
            item
            for item in rows
            if item.chat_id == record.chat_id
            and item.thread_id == record.thread_id
            and item.platform == record.platform
        ),
        None,
    )
    return {
        "route": target.to_public_dict() if target is not None else None,
        "routes": [item.to_public_dict() for item in rows],
    }


def delete_messaging_destination(orchestrator: "Orchestrator", *, destination_id: str) -> dict[str, Any]:
    """Delete one messaging destination by id."""
    target_id = str(destination_id or "").strip()
    if not target_id:
        raise ValueError("destinationId is required")
    before = orchestrator._messaging_store.load()
    existed = any(item.id == target_id for item in before.destinations)
    updated = orchestrator._messaging_store.delete_destination(target_id)
    return {
        "deleted": existed,
        "destinationId": target_id,
        "config": get_messaging_config(orchestrator),
    }


def delete_messaging_route(orchestrator: "Orchestrator", *, route_id: str) -> dict[str, Any]:
    """Delete one Telegram chat/thread route by id."""
    target_id = str(route_id or "").strip()
    if not target_id:
        raise ValueError("routeId is required")
    before = orchestrator._route_store.list_routes()
    existed = any(item.id == target_id for item in before)
    rows = orchestrator._route_store.delete_route(target_id)
    return {
        "deleted": existed,
        "routeId": target_id,
        "routes": [item.to_public_dict() for item in rows],
    }


def resolve_messaging_route(
    orchestrator: "Orchestrator",
    *,
    platform: str,
    chat_id: str,
    thread_id: str | None = None,
    create_if_missing: bool = False,
    title_hint: str | None = None,
) -> dict[str, Any]:
    """Resolve one Telegram chat/thread to a normal CopeNet session, optionally autocreating it."""
    target_platform = str(platform or "telegram").strip().lower() or "telegram"
    if target_platform != "telegram":
        raise ValueError(f"unsupported messaging platform: {platform}")
    normalized_chat_id = str(chat_id or "").strip()
    normalized_thread_id = str(thread_id).strip() if thread_id is not None and str(thread_id).strip() else None
    if not normalized_chat_id:
        raise ValueError("chatId is required")

    route = orchestrator._route_store.find_route(
        platform=target_platform,
        chat_id=normalized_chat_id,
        thread_id=normalized_thread_id,
    )
    entry = orchestrator._session_store.get(route.session_key) if route is not None else None
    if route is not None and entry is not None:
        return {
            "created": False,
            "route": route.to_public_dict(),
            "session": session_payload(entry),
        }
    if not create_if_missing:
        return {
            "created": False,
            "route": route.to_public_dict() if route is not None else None,
            "session": None,
        }

    defaults = orchestrator._messaging_store.load().telegram_defaults
    provider_id = _resolve_telegram_provider(orchestrator, defaults.provider if defaults is not None else None)
    system_prompt_id = defaults.system_prompt_id if defaults and defaults.system_prompt_id else "default"
    task_prompt_id = defaults.task_prompt_id if defaults and defaults.task_prompt_id else "none"
    created = create_session_with_profile(
        orchestrator,
        provider=provider_id,
        model=defaults.model if defaults is not None else None,
        title=_resolve_telegram_title(route, title_hint, normalized_chat_id),
        system_prompt_id=system_prompt_id,
        task_prompt_id=task_prompt_id,
        workspace_root=None,
    )
    route_rows = orchestrator._route_store.upsert_route(
        TelegramSessionRouteRecord(
            id=route.id if route is not None else "",
            platform=target_platform,
            chat_id=normalized_chat_id,
            thread_id=normalized_thread_id,
            session_key=created["key"],
            title_override=route.title_override if route is not None else (str(title_hint).strip() if title_hint else None),
        )
    )
    persisted_route = next(
        (
            item
            for item in route_rows
            if item.platform == target_platform
            and item.chat_id == normalized_chat_id
            and item.thread_id == normalized_thread_id
        ),
        None,
    )
    return {
        "created": True,
        "route": persisted_route.to_public_dict() if persisted_route is not None else None,
        "session": created,
    }


def _resolve_telegram_provider(orchestrator: "Orchestrator", preferred_provider: str | None) -> str:
    provider_id = str(preferred_provider or "").strip()
    if provider_id and provider_id in orchestrator._providers:
        return provider_id
    if "openai-codex" in orchestrator._providers:
        return "openai-codex"
    provider_ids = sorted(orchestrator._providers)
    if provider_ids:
        return provider_ids[0]
    raise RuntimeError("no providers available for Telegram session creation")


def _resolve_telegram_title(
    route: TelegramSessionRouteRecord | None,
    title_hint: str | None,
    chat_id: str,
) -> str:
    if route is not None and route.title_override:
        return route.title_override
    hinted = str(title_hint or "").strip()
    if hinted:
        return hinted
    return f"Telegram · {chat_id}"


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

    # We do NOT contact api.telegram.org here (the raw token is only stored
    # masked, and there is no delivery lane yet), so we must not claim the bot is
    # "connected" — that was a dishonest always-passes Test. Report the truth:
    # a token is present but unverified against Telegram.
    checked_at = utc_now_iso()
    refreshed = TelegramBotConfigRecord(
        bot_username=telegram.bot_username,
        token_masked=telegram.token_masked,
        connection_status="disconnected",
        last_verified_at=None,
        error_message=None,
    )
    orchestrator._messaging_store.update_telegram(refreshed)
    return {
        "platform": "telegram",
        "config": get_messaging_config(orchestrator),
        "result": {
            "ok": True,
            "connectionStatus": "disconnected",
            "message": "Token is configured but not verified — CopeNet does not perform a live Telegram check yet.",
            "verifiedAt": None,
            "checkedAt": checked_at,
        },
    }
