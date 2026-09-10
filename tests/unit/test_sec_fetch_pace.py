"""CopeNet's SEC request budget.

SEC enforces fair access with a **non-retryable 403** — CopeTech-Edgar retries 429/503 with
`Retry-After`, but a 403 aborts. So the budget is not a performance knob, it is the thing
standing between a backfill and a dead one, and it gets pinned.
"""

from __future__ import annotations

import asyncio
import importlib
import logging

import pytest

from copenet.core.market import sec_fetcher


def reload_with(monkeypatch, **env) -> object:
    for key, value in env.items():
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)
    return importlib.reload(sec_fetcher)


@pytest.fixture(autouse=True)
def _restore_module():
    """The module reads env at import, so every test that reloads it must put it back —
    otherwise a clamped interval leaks into whatever runs next."""
    yield
    importlib.reload(sec_fetcher)


class RecordingFetcher:
    """Stands in for SECDataFetcher / EdgarClient: both take exactly these kwargs."""

    def __init__(self, user_agent: str, rate_limit_sleep: float = 0.1, cache_dir: str = "data/edgar"):
        self.user_agent = user_agent
        self.rate_limit_sleep = rate_limit_sleep
        self.cache_dir = cache_dir
        self.closed = False

    async def close(self) -> None:
        self.closed = True


def build(**kwargs) -> RecordingFetcher:
    async def run():
        async with sec_fetcher.managed_sec_fetcher(RecordingFetcher, **kwargs) as fetcher:
            return fetcher

    return asyncio.run(run())


# --------------------------------------------------------------------------- the interval


def test_the_default_leaves_headroom_under_secs_ceiling(monkeypatch):
    reload_with(monkeypatch, COPNET_SEC_FETCH_PACE=None)

    assert sec_fetcher.SEC_FETCH_PACE > sec_fetcher.SEC_CEILING_PACE, (
        "defaulting to SEC's exact 10 req/s ceiling leaves no room for a retry burst, "
        "and the penalty for crossing it is a 403 that never retries"
    )


def test_a_slower_interval_is_honoured_for_bulk_pulls(monkeypatch):
    module = reload_with(monkeypatch, COPNET_SEC_FETCH_PACE="0.25")

    assert module.SEC_FETCH_PACE == 0.25


def test_a_faster_interval_than_sec_allows_is_clamped_not_obeyed(monkeypatch, caplog):
    with caplog.at_level(logging.WARNING):
        module = reload_with(monkeypatch, COPNET_SEC_FETCH_PACE="0.02")

    assert module.SEC_FETCH_PACE == module.SEC_CEILING_PACE
    assert "ceiling" in caplog.text


def test_a_junk_interval_falls_back_to_the_default_rather_than_crashing_startup(monkeypatch, caplog):
    with caplog.at_level(logging.WARNING):
        module = reload_with(monkeypatch, COPNET_SEC_FETCH_PACE="banana")

    assert module.SEC_FETCH_PACE == module.DEFAULT_SEC_FETCH_PACE
    assert "not a number" in caplog.text


# ------------------------------------------------------------------------- the boundary


def test_every_fetcher_inherits_the_budget_without_the_call_site_asking(monkeypatch):
    """The five construction sites in edgar.py and financials.py pass no interval. If the
    boundary stopped defaulting it, they would all silently revert to SEC's ceiling."""
    module = reload_with(monkeypatch, COPNET_SEC_FETCH_PACE="0.3")

    async def run():
        async with module.managed_sec_fetcher(RecordingFetcher) as fetcher:
            return fetcher

    assert asyncio.run(run()).rate_limit_sleep == 0.3


def test_a_caller_may_still_choose_to_go_slower():
    assert build(rate_limit_sleep=0.5).rate_limit_sleep == 0.5


def test_unrelated_fetcher_kwargs_still_pass_through():
    """financials.py builds EdgarClient with a cache_dir; the budget must not displace it."""
    fetcher = build(cache_dir="/tmp/edgar")

    assert fetcher.cache_dir == "/tmp/edgar"
    assert fetcher.rate_limit_sleep == sec_fetcher.SEC_FETCH_PACE


def test_the_fetcher_is_closed_even_when_the_body_raises():
    holder = {}

    async def run():
        with pytest.raises(RuntimeError):
            async with sec_fetcher.managed_sec_fetcher(RecordingFetcher) as fetcher:
                holder["fetcher"] = fetcher
                raise RuntimeError("boom")

    asyncio.run(run())
    assert holder["fetcher"].closed is True


# --------------------------------------------------------------------- the declared contact


def test_the_placeholder_contact_warns_because_upstream_cannot(monkeypatch, caplog):
    """CopeTech-Edgar only warns when the agent is *empty*. CopeNet always passes a
    non-empty default, which silences that check — so the check has to live here."""
    module = reload_with(monkeypatch, SEC_API_USER_AGENT=None)

    with caplog.at_level(logging.WARNING):
        async def run():
            async with module.managed_sec_fetcher(RecordingFetcher):
                pass

        asyncio.run(run())

    assert module.UNCONFIGURED_CONTACT in caplog.text
    assert "403" in caplog.text


def test_a_real_contact_is_used_and_warns_about_nothing(monkeypatch, caplog):
    module = reload_with(monkeypatch, SEC_API_USER_AGENT="Pat Example pat@example.org")

    with caplog.at_level(logging.WARNING):
        async def run():
            async with module.managed_sec_fetcher(RecordingFetcher) as fetcher:
                return fetcher

        fetcher = asyncio.run(run())

    assert fetcher.user_agent == "Pat Example pat@example.org"
    assert "placeholder" not in caplog.text


def test_the_contact_warning_fires_once_not_once_per_request(monkeypatch, caplog):
    """Every SEC call builds a fetcher. Warning per call would bury the message in exactly
    the request volume it is warning about."""
    module = reload_with(monkeypatch, SEC_API_USER_AGENT=None)

    with caplog.at_level(logging.WARNING):
        async def run():
            for _ in range(4):
                async with module.managed_sec_fetcher(RecordingFetcher):
                    pass

        asyncio.run(run())

    assert caplog.text.count("placeholder contact") == 1
