"""Lifecycle boundary for CopeTech-Edgar fetchers — and CopeNet's SEC request budget.

Every fetcher CopeNet builds is constructed here, which makes this the only place the
request rate and the declared contact can be set. That matters because SEC enforces its
fair-access policy with **403, and 403 is not retryable**: CopeTech-Edgar backs off and
retries 429/503 with `Retry-After`, but a 403 aborts the request outright. Getting the
budget wrong is not a slow scan, it is a dead one.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
import logging
import os
from typing import Any, AsyncIterator

logger = logging.getLogger(__name__)

# SEC's documented fair-access ceiling is 10 requests/second. CopeTech-Edgar defaults to
# exactly that (0.1s), which leaves no headroom at all: one retry burst, a coarse clock, or
# a second CopeNet process sharing the IP puts the host over the line, and the penalty is a
# non-retryable 403 rather than a throttle. A multi-hour backfill finishes at 6.7/s about as
# soon as it does at 10/s, so the default gives the margin back.
SEC_CEILING_INTERVAL = 0.1
DEFAULT_SEC_REQUEST_INTERVAL = 0.15


def _resolve_interval() -> float:
    """Seconds between SEC requests. Never below SEC's own ceiling, whatever is configured.

    Raise `COPNET_SEC_REQUEST_INTERVAL` for a bulk pull — a five-year backfill across a
    wide universe is tens of thousands of requests, and there is no hurry.
    """
    raw = os.environ.get("COPNET_SEC_REQUEST_INTERVAL", "").strip()
    if not raw:
        return DEFAULT_SEC_REQUEST_INTERVAL
    try:
        requested = float(raw)
    except ValueError:
        logger.warning(
            "COPNET_SEC_REQUEST_INTERVAL=%r is not a number — using the default %.2fs.",
            raw, DEFAULT_SEC_REQUEST_INTERVAL,
        )
        return DEFAULT_SEC_REQUEST_INTERVAL
    if requested < SEC_CEILING_INTERVAL:
        logger.warning(
            "COPNET_SEC_REQUEST_INTERVAL=%.3fs is faster than SEC's 10 req/s ceiling — clamping to %.2fs.",
            requested, SEC_CEILING_INTERVAL,
        )
        return SEC_CEILING_INTERVAL
    return requested


SEC_REQUEST_INTERVAL = _resolve_interval()

# SEC requires a declared contact on every request and blocks callers who do not send one.
# The placeholder is deliberately kept obviously fake rather than plausible: CopeTech-Edgar
# only warns when the agent is *empty*, so a plausible-looking default would silence its
# check while still sending SEC an address that does not reach anybody.
UNCONFIGURED_CONTACT = "contact@example.com"
SEC_API_USER_AGENT = os.environ.get(
    "SEC_API_USER_AGENT",
    f"CopeNet/0.1 {UNCONFIGURED_CONTACT}",
).strip()

_CONTACT_WARNED = False


def _warn_once_about_contact() -> None:
    """One warning per process. Every SEC call passes through here, so warning per call
    would bury the message in the volume it is trying to describe."""
    global _CONTACT_WARNED
    if _CONTACT_WARNED or UNCONFIGURED_CONTACT not in SEC_API_USER_AGENT:
        return
    _CONTACT_WARNED = True
    logger.warning(
        "SEC requests are going out with the placeholder contact %r. SEC's fair-access "
        "policy requires a real address and enforces it with a non-retryable 403. Set "
        "SEC_API_USER_AGENT='Your Name your@email.com' in .copenet.env before any bulk pull.",
        SEC_API_USER_AGENT,
    )


@asynccontextmanager
async def managed_sec_fetcher(
    fetcher_class: Any, *, user_agent: str | None = None, **fetcher_kwargs: Any
) -> AsyncIterator[Any]:
    """Build, yield and close one CopeTech-Edgar fetcher on CopeNet's request budget.

    `rate_limit_sleep` is defaulted rather than forced so a caller with a reason to go
    slower still can; nothing in the tree currently has one.
    """
    _warn_once_about_contact()
    fetcher_kwargs.setdefault("rate_limit_sleep", SEC_REQUEST_INTERVAL)
    fetcher = fetcher_class(user_agent=user_agent or SEC_API_USER_AGENT, **fetcher_kwargs)
    try:
        yield fetcher
    finally:
        close = getattr(fetcher, "close", None)
        if close is not None:
            await close()
