"""External-app facade methods."""

from __future__ import annotations



class AppFacadeMixin:
    def register_app(
        self,
        *,
        app_id: str,
        display_name: str | None = None,
        token: str | None = None,
        default_provider: str | None = None,
        default_model: str | None = None,
        allow_tools: bool = False,
    ) -> tuple[dict, str]:
        """Register an external app and return the stored metadata plus plain token."""
        entry, plain_token = self._app_store.register_app(
            app_id=app_id,
            display_name=display_name,
            token=token,
            default_provider=default_provider,
            default_model=default_model,
            allow_tools=allow_tools,
        )
        return {
            "appId": entry.app_id,
            "displayName": entry.display_name,
            "createdAt": entry.created_at,
            "updatedAt": entry.updated_at,
            "defaultProvider": entry.default_provider,
            "defaultModel": entry.default_model,
            "allowTools": entry.allow_tools,
        }, plain_token
