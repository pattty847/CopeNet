"""Provider-auth facade methods for the orchestrator."""

from __future__ import annotations



class ProviderAuthFacadeMixin:
    def provider_auth_status(self, provider_id: str) -> dict:
        """Resolve auth status for a provider that owns local auth state."""
        provider = self._providers.get(provider_id.strip())
        auth_service = getattr(provider, "auth_service", None)
        if auth_service is None or not hasattr(auth_service, "status"):
            raise ValueError(f"provider does not expose auth management: {provider_id}")
        return auth_service.status()

    def provider_auth_begin_login(self, provider_id: str, redirect_uri: str | None = None) -> dict:
        """Start an interactive provider auth login flow."""
        provider = self._providers.get(provider_id.strip())
        auth_service = getattr(provider, "auth_service", None)
        if auth_service is None or not hasattr(auth_service, "begin_login"):
            raise ValueError(f"provider does not expose auth management: {provider_id}")
        return auth_service.begin_login(redirect_uri=redirect_uri)

    def provider_auth_complete_login(
        self,
        provider_id: str,
        *,
        login_token: str,
        redirect_url: str | None = None,
        code: str | None = None,
        state: str | None = None,
    ) -> dict:
        """Finish an interactive provider auth login flow."""
        provider = self._providers.get(provider_id.strip())
        auth_service = getattr(provider, "auth_service", None)
        if auth_service is None or not hasattr(auth_service, "complete_login"):
            raise ValueError(f"provider does not expose auth management: {provider_id}")
        return auth_service.complete_login(
            login_token=login_token,
            redirect_url=redirect_url,
            code=code,
            state=state,
        )

    def provider_auth_logout(self, provider_id: str) -> dict:
        """Clear provider-owned local auth state."""
        provider = self._providers.get(provider_id.strip())
        auth_service = getattr(provider, "auth_service", None)
        if auth_service is None or not hasattr(auth_service, "logout"):
            raise ValueError(f"provider does not expose auth management: {provider_id}")
        return auth_service.logout()
