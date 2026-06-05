"""Web search + fetch tools — break the "only knows the repo" ceiling.

Two read-only tools that ground the agent to the live web:

- ``web.search`` runs a query and returns ranked {title, url, snippet} results.
  Backed by DuckDuckGo's keyless HTML endpoint (no API key, no account).
- ``web.fetch`` pulls one URL and returns its readable text (boilerplate
  stripped) via the shared :class:`WebIngestionService`.

Both are ``side_effect="external"`` (they touch the network) but carry no write
risk, so they sit in the ``web`` category which is auto-allowed in every task
mode. The single network boundary is :func:`_http_get_text`; tests monkeypatch
it so nothing in the suite reaches the real internet.
"""

from __future__ import annotations

import asyncio
import re
from html import unescape
from urllib import error, parse, request

from copenet.core.tools.contracts import (
    ToolDescriptor,
    ToolExecutionContext,
    ToolExecutionRequest,
    ToolExecutionResult,
)
from copenet.core.web_ingest import WebIngestError, WebIngestionService

_USER_AGENT = "CopeNet/0.1 (+https://github.com/pattty847/CopeNet)"
_SEARCH_ENDPOINT = "https://html.duckduckgo.com/html/"
SEARCH_RESULT_LIMIT = 8
SEARCH_SNIPPET_CHARS = 300
FETCH_MAX_CHARS = 12000

# One DuckDuckGo HTML result row: a result__a anchor (url + title) optionally
# followed by a result__snippet anchor. We capture each separately and zip them
# in document order — the endpoint emits them paired and in rank order.
_RESULT_ANCHOR_RE = re.compile(
    r'<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
    re.DOTALL | re.IGNORECASE,
)
_SNIPPET_RE = re.compile(
    r'<a[^>]+class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</a>',
    re.DOTALL | re.IGNORECASE,
)
_TAG_RE = re.compile(r"<[^>]+>")


def _http_get_text(url: str, *, data: dict[str, str] | None = None, timeout: float = 15.0) -> str:
    """Fetch a URL and return decoded text. The single network boundary here."""
    body = parse.urlencode(data).encode("utf-8") if data else None
    req = request.Request(
        url,
        data=body,
        headers={
            "User-Agent": _USER_AGENT,
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.5",
        },
        method="POST" if body else "GET",
    )
    with request.urlopen(req, timeout=timeout) as response:  # noqa: S310 - fixed endpoint
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def _strip_html(fragment: str) -> str:
    return unescape(_TAG_RE.sub("", fragment or "")).strip()


def _decode_result_url(href: str) -> str:
    """Resolve DuckDuckGo's /l/?uddg= redirect wrapper to the real target URL."""
    raw = href.strip()
    if raw.startswith("//"):
        raw = "https:" + raw
    parsed = parse.urlparse(raw)
    if parsed.path.startswith("/l/") and "duckduckgo.com" in parsed.netloc:
        uddg = parse.parse_qs(parsed.query).get("uddg")
        if uddg:
            return parse.unquote(uddg[0])
    return raw


def _parse_search_results(html_text: str, *, limit: int) -> list[dict[str, str]]:
    anchors = _RESULT_ANCHOR_RE.findall(html_text)
    snippets = _SNIPPET_RE.findall(html_text)
    results: list[dict[str, str]] = []
    for index, (href, title_html) in enumerate(anchors):
        title = _strip_html(title_html)
        url = _decode_result_url(href)
        if not title or not url:
            continue
        snippet = _strip_html(snippets[index]) if index < len(snippets) else ""
        results.append({"title": title, "url": url, "snippet": snippet[:SEARCH_SNIPPET_CHARS]})
        if len(results) >= limit:
            break
    return results


async def search_web(request: ToolExecutionRequest, context: ToolExecutionContext) -> ToolExecutionResult:
    query = str(request.arguments.get("query") or "").strip()
    if not query:
        raise ValueError("query is required")
    raw_limit = request.arguments.get("limit")
    try:
        limit = int(raw_limit) if raw_limit is not None else SEARCH_RESULT_LIMIT
    except (TypeError, ValueError):
        limit = SEARCH_RESULT_LIMIT
    limit = max(1, min(limit, SEARCH_RESULT_LIMIT))

    try:
        html_text = await asyncio.to_thread(_http_get_text, _SEARCH_ENDPOINT, data={"q": query})
    except error.HTTPError as exc:
        raise RuntimeError(f"web search failed: HTTP {exc.code}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"web search failed: {exc.reason}") from exc

    results = _parse_search_results(html_text, limit=limit)
    if not results:
        return ToolExecutionResult(
            tool_id=request.tool_id,
            ok=True,
            summary=f"No web results for '{query}'",
            output={"query": query, "results": []},
        )
    summary = f"{len(results)} web result{'s' if len(results) != 1 else ''} for '{query}' — top: {results[0]['title']}"
    return ToolExecutionResult(
        tool_id=request.tool_id,
        ok=True,
        summary=summary,
        output={"query": query, "results": results},
    )


async def fetch_web(request: ToolExecutionRequest, context: ToolExecutionContext) -> ToolExecutionResult:
    url = str(request.arguments.get("url") or "").strip()
    if not url:
        raise ValueError("url is required")
    raw_max = request.arguments.get("maxChars")
    try:
        max_chars = int(raw_max) if raw_max is not None else FETCH_MAX_CHARS
    except (TypeError, ValueError):
        max_chars = FETCH_MAX_CHARS
    max_chars = max(500, min(max_chars, FETCH_MAX_CHARS))

    service = WebIngestionService(user_agent=_USER_AGENT)
    try:
        extracted = await service.extract_url(url=url, max_chars=max_chars)
    except WebIngestError as exc:
        raise RuntimeError(str(exc)) from exc

    summary = f"Fetched '{extracted.title}' ({extracted.word_count} words) from {extracted.url}"
    return ToolExecutionResult(
        tool_id=request.tool_id,
        ok=True,
        summary=summary,
        output={
            "url": extracted.url,
            "title": extracted.title,
            "text": extracted.text,
            "excerpt": extracted.excerpt,
            "wordCount": extracted.word_count,
        },
    )


DESCRIPTORS = [
    ToolDescriptor(
        id="web.search",
        name="Search Web",
        description=(
            "Search the live web for current information you don't already have — docs, error messages, "
            "library APIs, recent events. Returns ranked results as {title, url, snippet}. Use a focused "
            "query, then call web.fetch on the most relevant URL to read the full page. Prefer this over "
            "guessing when a question depends on facts outside the repository."
        ),
        category="web",
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The search query."},
                "limit": {
                    "type": "integer",
                    "description": f"Max results to return (1-{SEARCH_RESULT_LIMIT}, default {SEARCH_RESULT_LIMIT}).",
                },
            },
            "required": ["query"],
            "additionalProperties": False,
        },
        capabilities=["web-search"],
        evidence_role="discovery",
        side_effect="external",
    ),
    ToolDescriptor(
        id="web.fetch",
        name="Fetch Web Page",
        description=(
            "Fetch one URL and return its readable text content with boilerplate stripped. Use this after "
            "web.search to read a promising result, or directly when you already have the URL. Returns the "
            "page title and cleaned text (truncated). HTML and plain-text pages only."
        ),
        category="web",
        input_schema={
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "The page URL to fetch (http/https)."},
                "maxChars": {
                    "type": "integer",
                    "description": f"Max characters of text to return (default {FETCH_MAX_CHARS}).",
                },
            },
            "required": ["url"],
            "additionalProperties": False,
        },
        capabilities=["web-fetch"],
        evidence_role="grounding",
        side_effect="external",
    ),
]

HANDLERS = {"web.search": search_web, "web.fetch": fetch_web}
