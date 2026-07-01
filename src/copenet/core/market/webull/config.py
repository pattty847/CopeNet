"""Webull configuration — env-only credentials, structurally unprintable.

Reads (loaded from `.env` at startup by copenet._env.load_project_env):
- WEBULL_KEY / WEBULL_SECRET  (app credentials; required)
- WEBULL_ENV                  (production | sandbox; default production)
- INCLUDE_WEBULL_PORTFOLIO_CONTEXT (true|false; default false — gates the model context pack)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

_UAT_HOST = "us-openapi-alb.uat.webullbroker.com"


@dataclass(frozen=True)
class WebullConfig:
    # repr=False so no dataclass repr, log line, or traceback ever prints the secrets.
    app_key: str = field(repr=False)
    app_secret: str = field(repr=False)
    env: str = "production"
    include_portfolio_context: bool = False

    def __repr__(self) -> str:  # defense in depth on top of repr=False
        return f"WebullConfig(env={self.env!r}, include_portfolio_context={self.include_portfolio_context}, app_key=***, app_secret=***)"

    __str__ = __repr__

    @property
    def uat_host(self) -> str | None:
        return _UAT_HOST if self.env == "sandbox" else None


def include_portfolio_context_enabled() -> bool:
    return os.environ.get("INCLUDE_WEBULL_PORTFOLIO_CONTEXT", "").strip().lower() in {"1", "true", "yes", "on"}


def load_webull_config() -> WebullConfig | None:
    """Return the config, or None when credentials are absent (feature stays dormant)."""
    key = os.environ.get("WEBULL_KEY", "").strip()
    secret = os.environ.get("WEBULL_SECRET", "").strip()
    if not key or not secret:
        return None
    env = os.environ.get("WEBULL_ENV", "production").strip().lower()
    if env not in {"production", "sandbox"}:
        env = "production"
    return WebullConfig(
        app_key=key,
        app_secret=secret,
        env=env,
        include_portfolio_context=include_portfolio_context_enabled(),
    )
