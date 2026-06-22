"""Messaging facade methods for the orchestrator."""

from __future__ import annotations

from copenet.core.orchestrator.messaging import (
    delete_messaging_destination as delete_messaging_destination_record,
    delete_messaging_route as delete_messaging_route_record,
    get_messaging_config as get_messaging_config_record,
    list_messaging_destinations as list_messaging_destinations_record,
    list_messaging_routes as list_messaging_routes_record,
    resolve_messaging_route as resolve_messaging_route_record,
    test_messaging_platform as test_messaging_platform_record,
    update_messaging_config as update_messaging_config_record,
    upsert_messaging_destination as upsert_messaging_destination_record,
    upsert_messaging_route as upsert_messaging_route_record,
)


class MessagingFacadeMixin:
    def get_messaging_config(self) -> dict:
        """Return the persisted operator messaging configuration."""
        return get_messaging_config_record(self)

    def update_messaging_config(self, *, approval_policy: dict | None = None, telegram_defaults: dict | None = None) -> dict:
        """Persist a minimal messaging configuration patch."""
        return update_messaging_config_record(self, approval_policy=approval_policy, telegram_defaults=telegram_defaults)

    def test_messaging_platform(self, platform: str = "telegram") -> dict:
        """Run a conservative local messaging config test."""
        return test_messaging_platform_record(self, platform=platform)

    def list_messaging_destinations(self) -> list[dict]:
        """Return configured messaging destinations."""
        return list_messaging_destinations_record(self)

    def upsert_messaging_destination(self, *, destination: dict) -> dict:
        """Create or update one messaging destination."""
        return upsert_messaging_destination_record(self, destination=destination)

    def delete_messaging_destination(self, *, destination_id: str) -> dict:
        """Delete one messaging destination."""
        return delete_messaging_destination_record(self, destination_id=destination_id)

    def list_messaging_routes(self) -> list[dict]:
        """Return configured Telegram chat-to-session routes."""
        return list_messaging_routes_record(self)

    def upsert_messaging_route(self, *, route: dict) -> dict:
        """Create or update one Telegram route mapping."""
        return upsert_messaging_route_record(self, route=route)

    def delete_messaging_route(self, *, route_id: str) -> dict:
        """Delete one Telegram route mapping."""
        return delete_messaging_route_record(self, route_id=route_id)

    def resolve_messaging_route(
        self,
        *,
        platform: str,
        chat_id: str,
        thread_id: str | None = None,
        create_if_missing: bool = False,
        title_hint: str | None = None,
    ) -> dict:
        """Resolve or autocreate the CopeNet session backing one messaging conversation."""
        return resolve_messaging_route_record(
            self,
            platform=platform,
            chat_id=chat_id,
            thread_id=thread_id,
            create_if_missing=create_if_missing,
            title_hint=title_hint,
        )
