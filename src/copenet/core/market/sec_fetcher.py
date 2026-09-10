"""Lifecycle boundary for CopeTech-Edgar fetchers — and CopeNet's SEC request budget.

Every fetcher CopeNet builds is constructed here, which makes this the only place the
request pace and the declared contact can be set. That matters because SEC enforces its
fair-access policy with **403, and 403 is not retryable**: CopeTech-Edgar backs off and
retries 429/503 with `Retry-After`, but a 403 aborts the request outright. Getting the
budget wrong is not a slow scan, it is a dead one.

Both settings are read when a fetcher is built, never at import. `copenet._env` populates
`os.environ` from `.env` inside `main()`, but importing the host pulls this module in
through the orchestrator first — so a module-level `os.environ.get` would resolve before
`.env` was ever read and silently ignore whatever the operator configured. `NasaService`
reads `NASA_API_KEY` in its constructor for the same reason; this follows it.
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
SEC_CEILING_PACE = 0.1
DEFAULT_SEC_FETCH_PACE = 0.15

# SEC requires a declared contact on every request and blocks callers who do not send one.
# The placeholder is deliberately obviously fake rather than plausible: CopeTech-Edgar only
# warns when the agent is *empty*, so a plausible default would silence its check while
# still sending SEC an address that reaches nobody.
UNCONFIGURED_CONTACT = "contact@example.com"
DEFAULT_SEC_USER_AGENT = f"CopeNet/0.1 {UNCONFIGURED_CONTACT}"

# One warning per problem per process. Every SEC call builds a fetcher, so warning per call
# would bury each message in exactly the request volume it is describing.
_WARNED: set[str] = set()


def _warn_once(key: str, message: str, *args: Any) -> None:
    if key in _WARNED:
        return
    _WARNED.add(key)
    logger.warning(message, *args)


def sec_fetch_pace() -> float:
    """Seconds between SEC requests — the SEC counterpart to `COPNET_MARKET_FETCH_PACE`,
    which paces yfinance. Never below SEC's own ceiling, whatever is configured.

    Raise `COPNET_SEC_FETCH_PACE` for a bulk pull: a multi-year backfill across a wide
    universe is tens of thousands of requests, and there is no hurry.
    """
    raw = os.environ.get("COPNET_SEC_FETCH_PACE", "").strip()
    if not raw:
        return DEFAULT_SEC_FETCH_PACE
    try:
        requested = float(raw)
    except ValueError:
        _warn_once(
            "pace-nan",
            "COPNET_SEC_FETCH_PACE=%r is not a number — using the default %.2fs.",
            raw, DEFAULT_SEC_FETCH_PACE,
        )
        return DEFAULT_SEC_FETCH_PACE
    if requested < SEC_CEILING_PACE:
        _warn_once(
            "pace-clamped",
            "COPNET_SEC_FETCH_PACE=%.3fs is faster than SEC's 10 req/s ceiling — clamping to %.2fs.",
            requested, SEC_CEILING_PACE,
        )
        return SEC_CEILING_PACE
    return requested


def sec_user_agent() -> str:
    """The contact SEC sees. Set `SEC_API_USER_AGENT` in `.env`, beside the other feature
    credentials — `.copenet.env` is the gateway token and is loaded by a different path."""
    agent = os.environ.get("SEC_API_USER_AGENT", DEFAULT_SEC_USER_AGENT).strip() or DEFAULT_SEC_USER_AGENT
    if UNCONFIGURED_CONTACT in agent:
        _warn_once(
            "contact",
            "SEC requests are going out with the placeholder contact %r. SEC's fair-access "
            "policy requires a real address and enforces it with a non-retryable 403. Set "
            "SEC_API_USER_AGENT='Your Name your@email.com' in .env before any bulk pull.",
            agent,
        )
    return agent


@asynccontextmanager
async def managed_sec_fetcher(
    fetcher_class: Any, *, user_agent: str | None = None, **fetcher_kwargs: Any
) -> AsyncIterator[Any]:
    """Build, yield and close one CopeTech-Edgar fetcher on CopeNet's request budget.

    `rate_limit_sleep` is defaulted rather than forced so a caller with a reason to go
    slower still can; nothing in the tree currently has one.
    """
    fetcher_kwargs.setdefault("rate_limit_sleep", sec_fetch_pace())
    fetcher = fetcher_class(user_agent=user_agent or sec_user_agent(), **fetcher_kwargs)
    try:
        yield fetcher
    finally:
        close = getattr(fetcher, "close", None)
        if close is not None:
            await close()
