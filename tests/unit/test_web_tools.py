"""web.search + web.fetch — the agent's window to the live web.

The real I/O boundaries (`_http_get_text`, the WebIngestionService HTTP call,
and the `_fetch_via_openai_codex` fallback) are monkeypatched, so these tests
never touch the network.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from copenet.core.tools import ToolExecutionRequest, ToolPolicy, ToolRegistry
from copenet.core.tools.contracts import ToolExecutionContext
from copenet.core.tools.handlers import web as web_handler
from copenet.core.sessions.session_store import SessionStore
from copenet.core.sessions.transcript_store import TranscriptStore
from copenet.core.web_ingest import WebExtractResult, WebIngestError


def _ctx(tmp_path: Path) -> ToolExecutionContext:
    return ToolExecutionContext(
        workdir=tmp_path,
        session_workspace_root=tmp_path,
        session_key="s",
        provider_name="t",
        model="t",
        session_store=SessionStore(path=tmp_path / "i.json"),
        transcript_store=TranscriptStore(root_dir=tmp_path),
        providers={},
        policy=ToolPolicy(allowed_categories={"web"}),
    )


_DDG_HTML = """
<div class="result">
  <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fdocs.python.org%2F3%2F&amp;rut=x">Python <b>Docs</b></a>
  <a class="result__snippet">The official <b>Python</b> documentation.</a>
</div>
<div class="result">
  <a class="result__a" href="https://example.com/two">Second Result</a>
  <a class="result__snippet">A second snippet.</a>
</div>
"""


@pytest.mark.asyncio
async def test_web_search_parses_ranked_results(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_get(url: str, *, data=None, timeout: float = 15.0) -> str:
        captured["url"] = url
        captured["data"] = data
        return _DDG_HTML

    monkeypatch.setattr(web_handler, "_http_get_text", fake_get)

    result = await ToolRegistry().execute(
        ToolExecutionRequest(tool_id="web.search", arguments={"query": "python docs"}),
        _ctx(tmp_path),
    )
    assert result.ok is True
    results = result.output["results"]
    assert len(results) == 2
    # DDG redirect wrapper is decoded back to the real target URL + tags stripped.
    assert results[0] == {
        "title": "Python Docs",
        "url": "https://docs.python.org/3/",
        "snippet": "The official Python documentation.",
    }
    assert results[1]["url"] == "https://example.com/two"
    assert captured["data"] == {"q": "python docs"}


@pytest.mark.asyncio
async def test_web_search_results_are_not_treated_as_failed_batch_members(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Regression: web.search returns a "results" list of plain {title,url,snippet}
    # rows. The batch-member expander keys on a "results" list too, and must NOT
    # mistake these for failed sub-tools (they carry no toolId).
    monkeypatch.setattr(web_handler, "_http_get_text", lambda *a, **k: _DDG_HTML)
    result = await ToolRegistry().execute(
        ToolExecutionRequest(tool_id="web.search", arguments={"query": "python docs"}),
        _ctx(tmp_path),
    )
    payload = result.to_event_payload()
    assert "members" not in payload  # not an exploded (and falsely-failed) batch


@pytest.mark.asyncio
async def test_web_search_requires_query(tmp_path: Path) -> None:
    result = await ToolRegistry().execute(
        ToolExecutionRequest(tool_id="web.search", arguments={"query": "   "}),
        _ctx(tmp_path),
    )
    assert result.ok is False


@pytest.mark.asyncio
async def test_web_search_clamps_limit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(web_handler, "_http_get_text", lambda *a, **k: _DDG_HTML)
    result = await ToolRegistry().execute(
        ToolExecutionRequest(tool_id="web.search", arguments={"query": "x", "limit": 1}),
        _ctx(tmp_path),
    )
    assert len(result.output["results"]) == 1


@pytest.mark.asyncio
async def test_web_search_emits_preview(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(web_handler, "_http_get_text", lambda *a, **k: _DDG_HTML)
    result = await ToolRegistry().execute(
        ToolExecutionRequest(tool_id="web.search", arguments={"query": "python docs"}),
        _ctx(tmp_path),
    )
    preview = result.to_event_payload().get("preview")
    assert preview["type"] == "web_search"
    assert preview["query"] == "python docs"
    assert preview["results"][0]["url"] == "https://docs.python.org/3/"


@pytest.mark.asyncio
async def test_web_fetch_returns_readable_text(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_extract(self, *, url: str, max_chars: int = 20000) -> WebExtractResult:
        return WebExtractResult(
            url="https://docs.python.org/3/",
            title="Python Docs",
            text="Readable body text about Python.",
            markdown="# Python Docs\n\nReadable body text about Python.\n",
            excerpt="Readable body text about Python.",
            word_count=5,
        )

    monkeypatch.setattr("copenet.core.web_ingest.WebIngestionService.extract_url", fake_extract)

    result = await ToolRegistry().execute(
        ToolExecutionRequest(tool_id="web.fetch", arguments={"url": "docs.python.org/3/"}),
        _ctx(tmp_path),
    )
    assert result.ok is True
    assert result.output["title"] == "Python Docs"
    assert result.output["wordCount"] == 5
    preview = result.to_event_payload().get("preview")
    assert preview["type"] == "web_doc"
    assert preview["url"] == "https://docs.python.org/3/"


@pytest.mark.asyncio
async def test_web_fetch_requires_url(tmp_path: Path) -> None:
    result = await ToolRegistry().execute(
        ToolExecutionRequest(tool_id="web.fetch", arguments={}),
        _ctx(tmp_path),
    )
    assert result.ok is False


@pytest.mark.asyncio
async def test_web_fetch_surfaces_ingest_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_extract(self, *, url: str, max_chars: int = 20000) -> WebExtractResult:
        raise WebIngestError("unsupported content type: application/pdf")

    monkeypatch.setattr("copenet.core.web_ingest.WebIngestionService.extract_url", fake_extract)

    result = await ToolRegistry().execute(
        ToolExecutionRequest(tool_id="web.fetch", arguments={"url": "https://x.test/a.pdf"}),
        _ctx(tmp_path),
    )
    assert result.ok is False
    assert "unsupported content type" in (result.error or "")


@pytest.mark.asyncio
async def test_web_fetch_falls_back_to_openai_codex_when_blocked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_extract(self, *, url: str, max_chars: int = 20000) -> WebExtractResult:
        raise WebIngestError("web fetch failed: HTTP 401")

    async def fake_fallback(url: str, *, max_chars: int) -> WebExtractResult:
        return WebExtractResult(
            url=url,
            title="Blocked Site Article",
            text="Digest gathered via the fallback path.",
            markdown="# Blocked Site Article\n\nDigest gathered via the fallback path.\n",
            excerpt="Digest gathered via the fallback path.",
            word_count=6,
        )

    monkeypatch.setattr("copenet.core.web_ingest.WebIngestionService.extract_url", fake_extract)
    monkeypatch.setattr(web_handler, "_fetch_via_openai_codex", fake_fallback)

    result = await ToolRegistry().execute(
        ToolExecutionRequest(tool_id="web.fetch", arguments={"url": "https://blocked.test/a"}),
        _ctx(tmp_path),
    )
    assert result.ok is True
    assert result.output["title"] == "Blocked Site Article"
    assert result.output["source"] == "openai_codex_web_search"


@pytest.mark.asyncio
async def test_web_fetch_unsupported_content_type_skips_openai_codex_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_extract(self, *, url: str, max_chars: int = 20000) -> WebExtractResult:
        raise WebIngestError("unsupported content type: application/pdf")

    async def unexpected_fallback(url: str, *, max_chars: int) -> WebExtractResult:
        raise AssertionError("fallback must not run for unsupported-content-type errors")

    monkeypatch.setattr("copenet.core.web_ingest.WebIngestionService.extract_url", fake_extract)
    monkeypatch.setattr(web_handler, "_fetch_via_openai_codex", unexpected_fallback)

    result = await ToolRegistry().execute(
        ToolExecutionRequest(tool_id="web.fetch", arguments={"url": "https://x.test/a.pdf"}),
        _ctx(tmp_path),
    )
    assert result.ok is False
    assert "unsupported content type" in (result.error or "")


@pytest.mark.asyncio
async def test_web_tools_blocked_when_category_disallowed(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    ctx = ToolExecutionContext(
        workdir=ctx.workdir,
        session_workspace_root=ctx.session_workspace_root,
        session_key=ctx.session_key,
        provider_name=ctx.provider_name,
        model=ctx.model,
        session_store=ctx.session_store,
        transcript_store=ctx.transcript_store,
        providers={},
        policy=ToolPolicy(allowed_categories={"repo-read"}),
    )
    result = await ToolRegistry().execute(
        ToolExecutionRequest(tool_id="web.search", arguments={"query": "x"}),
        ctx,
    )
    assert result.ok is False
    assert "category not allowed" in (result.error or "")
