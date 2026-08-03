"""Lifecycle boundary for CopeTech-Edgar fetchers."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator


@asynccontextmanager
async def managed_sec_fetcher(
    fetcher_class: Any, *, user_agent: str, **fetcher_kwargs: Any
) -> AsyncIterator[Any]:
    fetcher = fetcher_class(user_agent=user_agent, **fetcher_kwargs)
    try:
        yield fetcher
    finally:
        close = getattr(fetcher, "close", None)
        if close is not None:
            await close()
