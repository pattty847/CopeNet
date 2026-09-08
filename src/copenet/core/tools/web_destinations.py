"""Web destination allowlist and URL checks used by the Barricade egress gate."""
from __future__ import annotations

import ipaddress
import os

# Query-parameter names that suggest secret material is being smuggled in a URL.
_SECRET_HINTS = (
    "token",
    "secret",
    "password",
    "passwd",
    "api_key",
    "apikey",
    "authorization",
    "bearer",
    "session",
    "cookie",
)


# Destinations web.fetch/web.search may reach WITHOUT an operator approval prompt.
# Curated from what CopeNet's own subsystems already talk to (its configured
# search backends) plus common, low-risk reference sources. Anything else public
# still works — it just pauses for a one-time operator approval instead of being
# silently allowed, per the "read broadly, but ask about places you haven't
# vetted" model. Extend via COPNET_WEB_FETCH_ALLOWLIST (comma-separated apex
# domains, additive) rather than editing this constant.
DEFAULT_ALLOWED_FETCH_DOMAINS: frozenset[str] = frozenset(
    {
        # search backends CopeNet is already configured to call
        "api.exa.ai",
        "api.search.brave.com",
        "html.duckduckgo.com",
        # general reference / docs
        "en.wikipedia.org",
        "wikipedia.org",
        "github.com",
        "raw.githubusercontent.com",
        "developer.mozilla.org",
        # finance/market reference (aligned with Market Monitor's own data sources)
        "www.sec.gov",
        "data.sec.gov",
        "home.treasury.gov",
        "finance.yahoo.com",
    }
)

FETCH_ALLOWLIST_ENV = "COPNET_WEB_FETCH_ALLOWLIST"


def fetch_allowlist() -> set[str]:
    """Destinations web.fetch/web.search may reach without an approval prompt.

    Built-in defaults, unioned with operator-configured entries from
    COPNET_WEB_FETCH_ALLOWLIST. Additive: operators extend the safe defaults,
    they don't need to restate them.
    """
    operator_raw = os.environ.get(FETCH_ALLOWLIST_ENV, "")
    operator_entries = {host.strip().lower() for host in operator_raw.split(",") if host.strip()}
    return DEFAULT_ALLOWED_FETCH_DOMAINS | operator_entries


def host_matches_allowlist(hostname: str | None, allowlist: set[str]) -> bool:
    """True when `hostname` equals or is a subdomain of an entry in `allowlist`."""
    host = (hostname or "").lower().strip(".")
    if not host:
        return False
    return any(host == domain or host.endswith(f".{domain}") for domain in allowlist)


def is_private_host(hostname: str | None) -> bool:
    if not hostname:
        return False
    host = hostname.lower().strip("[]")
    if host in {"localhost", "metadata", "metadata.google.internal"}:
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved


def secret_hint_in_query(query: str) -> str | None:
    lowered = (query or "").lower()
    for hint in _SECRET_HINTS:
        if f"{hint}=" in lowered:
            return hint
    return None
