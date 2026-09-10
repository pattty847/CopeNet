"""CopeNet's SEC request budget.

SEC enforces fair access with a **non-retryable 403** — CopeTech-Edgar retries 429/503 with
`Retry-After`, but a 403 aborts. So the budget is not a performance knob, it is the thing
standing between a backfill and a dead one, and it gets pinned.
"""

from __future__ import annotations

import ast
import asyncio
import logging
import pathlib

import pytest

from copenet.core.market import sec_fetcher


@pytest.fixture(autouse=True)
def _clear_warn_once():
    """The module warns once per problem per process; tests assert on those warnings."""
    sec_fetcher._WARNED.clear()
    yield
    sec_fetcher._WARNED.clear()


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


# ------------------------------------------------------------------- read time, not import

def test_nothing_in_the_package_resolves_a_setting_at_import_time():
    """`copenet._env` populates os.environ from `.env` inside `main()`, but importing the
    host pulls the orchestrator — and everything under it — in first. A module-level
    `os.environ.get` therefore resolves before `.env` is read and silently ignores whatever
    the operator configured. This shipped exactly once, in this module, and cost an evening.
    """
    offenders: list[str] = []

    def env_key(call: ast.Call) -> str | None:
        func = call.func
        if not (isinstance(func, ast.Attribute) and func.attr in ("get", "getenv")):
            return None
        value = func.value
        if isinstance(value, ast.Attribute) and value.attr == "environ":
            pass
        elif isinstance(value, ast.Name) and value.id == "os" and func.attr == "getenv":
            pass
        else:
            return None
        first = call.args[0] if call.args else None
        return first.value if isinstance(first, ast.Constant) else "?"

    def scan(body, path: pathlib.Path) -> None:
        for node in body:
            # A def's body runs at call time, which is the safe pattern. A class body does
            # execute at import, so it is still scanned.
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if isinstance(node, ast.ClassDef):
                scan(node.body, path)
                continue
            for sub in ast.walk(node):
                if isinstance(sub, ast.Call) and (key := env_key(sub)):
                    offenders.append(f"{path}:{sub.lineno} reads {key} at import")

    for path in sorted(pathlib.Path("src/copenet").rglob("*.py")):
        scan(ast.parse(path.read_text(encoding="utf-8")).body, path)

    assert offenders == [], "read these in a function instead:\n  " + "\n  ".join(offenders)


# --------------------------------------------------------------------------- the pace

def test_the_default_leaves_headroom_under_secs_ceiling(monkeypatch):
    monkeypatch.delenv("COPNET_SEC_FETCH_PACE", raising=False)

    assert sec_fetcher.sec_fetch_pace() > sec_fetcher.SEC_CEILING_PACE, (
        "defaulting to SEC's exact 10 req/s ceiling leaves no room for a retry burst, "
        "and the penalty for crossing it is a 403 that never retries"
    )


def test_a_slower_pace_is_honoured_for_bulk_pulls(monkeypatch):
    monkeypatch.setenv("COPNET_SEC_FETCH_PACE", "0.25")

    assert sec_fetcher.sec_fetch_pace() == 0.25


def test_a_faster_pace_than_sec_allows_is_clamped_not_obeyed(monkeypatch, caplog):
    monkeypatch.setenv("COPNET_SEC_FETCH_PACE", "0.02")

    with caplog.at_level(logging.WARNING):
        pace = sec_fetcher.sec_fetch_pace()

    assert pace == sec_fetcher.SEC_CEILING_PACE
    assert "ceiling" in caplog.text


def test_a_junk_pace_falls_back_to_the_default_rather_than_crashing(monkeypatch, caplog):
    monkeypatch.setenv("COPNET_SEC_FETCH_PACE", "banana")

    with caplog.at_level(logging.WARNING):
        pace = sec_fetcher.sec_fetch_pace()

    assert pace == sec_fetcher.DEFAULT_SEC_FETCH_PACE
    assert "not a number" in caplog.text


# ------------------------------------------------------------------------- the boundary

def test_every_fetcher_inherits_the_budget_without_the_call_site_asking(monkeypatch):
    """The five construction sites in edgar.py and financials.py pass no pace. If the
    boundary stopped defaulting it, they would all silently revert to SEC's ceiling."""
    monkeypatch.setenv("COPNET_SEC_FETCH_PACE", "0.3")

    assert build().rate_limit_sleep == 0.3


def test_a_caller_may_still_choose_to_go_slower():
    assert build(rate_limit_sleep=0.5).rate_limit_sleep == 0.5


def test_unrelated_fetcher_kwargs_still_pass_through(monkeypatch):
    """financials.py builds EdgarClient with a cache_dir; the budget must not displace it."""
    monkeypatch.delenv("COPNET_SEC_FETCH_PACE", raising=False)
    fetcher = build(cache_dir="/tmp/edgar")

    assert fetcher.cache_dir == "/tmp/edgar"
    assert fetcher.rate_limit_sleep == sec_fetcher.DEFAULT_SEC_FETCH_PACE


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
    monkeypatch.delenv("SEC_API_USER_AGENT", raising=False)

    with caplog.at_level(logging.WARNING):
        agent = sec_fetcher.sec_user_agent()

    assert sec_fetcher.UNCONFIGURED_CONTACT in agent
    assert "403" in caplog.text
    assert ".env" in caplog.text


def test_a_real_contact_is_used_and_warns_about_nothing(monkeypatch, caplog):
    monkeypatch.setenv("SEC_API_USER_AGENT", "Pat Example pat@example.org")

    with caplog.at_level(logging.WARNING):
        fetcher = build()

    assert fetcher.user_agent == "Pat Example pat@example.org"
    assert "placeholder" not in caplog.text


def test_a_blank_contact_falls_back_rather_than_sending_an_empty_header(monkeypatch, caplog):
    monkeypatch.setenv("SEC_API_USER_AGENT", "   ")

    with caplog.at_level(logging.WARNING):
        agent = sec_fetcher.sec_user_agent()

    assert sec_fetcher.UNCONFIGURED_CONTACT in agent


def test_the_contact_warning_fires_once_not_once_per_request(monkeypatch, caplog):
    """Every SEC call builds a fetcher. Warning per call would bury the message in exactly
    the request volume it is warning about."""
    monkeypatch.delenv("SEC_API_USER_AGENT", raising=False)

    with caplog.at_level(logging.WARNING):
        for _ in range(4):
            build()

    assert caplog.text.count("placeholder contact") == 1
