"""Web search + fetch tools — break the "only knows the repo" ceiling.

Two read-only tools that ground the agent to the live web:

- ``web.search`` runs a query and returns ranked {title, url, snippet} results.
  Uses Exa's semantic search API when ``EXA_API_KEY`` is set (real ranking, no
  HTML-scrape fragility); falls back to DuckDuckGo's keyless HTML endpoint
  (no API key, no account) when it isn't.
- ``web.fetch`` pulls one URL and returns its readable text via the shared
  :class:`WebIngestionService`, which itself prefers Jina Reader over a
  homegrown boilerplate stripper (see ``web_ingest.py``).

Both are ``side_effect="external"`` (they touch the network) but carry no write
risk, so they sit in the ``web`` category which is auto-allowed in every task
mode. The default (keyless) network boundary is :func:`_http_get_text`; tests
monkeypatch it so nothing in the suite reaches the real internet. The Exa path
(:func:`_search_via_exa`) is a second, separate boundary — it's dormant unless
``EXA_API_KEY`` is set, which the test suite never does, so it stays inert
there without needing its own monkeypatch.

Set ``COPNET_WEB_FETCH_ALLOWLIST`` (comma-separated apex domains) to restrict
which hosts the model may fetch/surface — unset means unrestricted (today's
default). ``web.fetch`` hard-blocks any other host; ``web.search`` filters its
results down to matching hosts instead of erroring.
"""

from __future__ import annotations

import asyncio
import json
import os
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
_EXA_SEARCH_ENDPOINT = "https://api.exa.ai/search"
_EXA_API_KEY_ENV = "EXA_API_KEY"
_BRAVE_WEB_SEARCH_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"
_BRAVE_NEWS_SEARCH_ENDPOINT = "https://api.search.brave.com/res/v1/news/search"
_BRAVE_API_KEY_ENV = "BRAVE_API_KEY"
SEARCH_RESULT_LIMIT = 8
SEARCH_SNIPPET_CHARS = 300
FETCH_MAX_CHARS = 12000

# Model-initiated web.fetch/web.search are the tool where an autonomous agent picks
# its own URLs — a different trust boundary than user-pasted links (web_ingest.py's
# other callers, e.g. media ingestion). Comma-separated apex domains; unset/empty
# means unrestricted (today's default behavior). Matching includes subdomains, so
# "reuters.com" also allows "www.reuters.com".
_FETCH_ALLOWLIST_ENV = "COPNET_WEB_FETCH_ALLOWLIST"


def _fetch_allowlist() -> set[str]:
    raw = os.environ.get(_FETCH_ALLOWLIST_ENV, "")
    return {domain.strip().lower() for domain in raw.split(",") if domain.strip()}


def _host_allowed(hostname: str, allowlist: set[str]) -> bool:
    host = hostname.lower().strip(".")
    return any(host == domain or host.endswith(f".{domain}") for domain in allowlist)

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


def _search_via_exa(query: str, *, limit: int) -> list[dict[str, str]] | None:
    """Exa semantic search — returns None (never raises) on missing key or any failure,
    so the caller falls back to the keyless DuckDuckGo path without special-casing."""
    api_key = os.environ.get(_EXA_API_KEY_ENV, "").strip()
    if not api_key:
        return None
    payload = json.dumps(
        {
            "query": query,
            "numResults": limit,
            "type": "auto",
            "contents": {"text": {"maxCharacters": SEARCH_SNIPPET_CHARS}},
        }
    ).encode("utf-8")
    req = request.Request(
        _EXA_SEARCH_ENDPOINT,
        data=payload,
        headers={"Content-Type": "application/json", "x-api-key": api_key, "User-Agent": _USER_AGENT},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=15.0) as response:
            body = json.loads(response.read().decode("utf-8", errors="replace"))
    except Exception:
        return None
    raw_results = body.get("results") if isinstance(body, dict) else None
    if not isinstance(raw_results, list):
        return None
    results: list[dict[str, str]] = []
    for item in raw_results:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "").strip()
        title = str(item.get("title") or "").strip()
        if not url or not title:
            continue
        results.append({"title": title, "url": url, "snippet": str(item.get("text") or "").strip()[:SEARCH_SNIPPET_CHARS]})
        if len(results) >= limit:
            break
    return results or None


def _search_via_brave(query: str, *, limit: int, news: bool) -> list[dict[str, str]] | None:
    """Brave Search API — real indexed web/news search (not a scrape). Returns None (never raises)
    on missing key or any failure, so the caller falls back cleanly. News mode uses Brave's
    dedicated news endpoint, which returns actual dated articles rather than generic web pages —
    the DuckDuckGo fallback's "stock news" results are mostly quote-page boilerplate, this isn't."""
    api_key = os.environ.get(_BRAVE_API_KEY_ENV, "").strip()
    if not api_key:
        return None
    endpoint = _BRAVE_NEWS_SEARCH_ENDPOINT if news else _BRAVE_WEB_SEARCH_ENDPOINT
    url = f"{endpoint}?{parse.urlencode({'q': query, 'count': limit})}"
    # Deliberately no Accept-Encoding header — Brave only gzips when asked, and stdlib urllib
    # doesn't auto-decompress, so omitting it keeps the response body plain JSON.
    req = request.Request(
        url,
        headers={"Accept": "application/json", "X-Subscription-Token": api_key, "User-Agent": _USER_AGENT},
        method="GET",
    )
    try:
        with request.urlopen(req, timeout=15.0) as response:
            body = json.loads(response.read().decode("utf-8", errors="replace"))
    except Exception:
        return None
    # The news endpoint returns {"results": [...]} at the top level; the general web-search
    # endpoint nests its organic results under {"web": {"results": [...]}} alongside sibling
    # sections (videos, mixed, etc.) — two different shapes from the same API family.
    if news:
        raw_results = body.get("results") if isinstance(body, dict) else None
    else:
        web_section = body.get("web") if isinstance(body, dict) else None
        raw_results = web_section.get("results") if isinstance(web_section, dict) else None
    if not isinstance(raw_results, list):
        return None
    results: list[dict[str, str]] = []
    for item in raw_results:
        if not isinstance(item, dict):
            continue
        url_value = str(item.get("url") or "").strip()
        title = str(item.get("title") or "").strip()
        if not url_value or not title:
            continue
        snippet = str(item.get("description") or "").strip()
        age = item.get("age")
        if age:
            snippet = f"[{age}] {snippet}"
        results.append({"title": title, "url": url_value, "snippet": snippet[:SEARCH_SNIPPET_CHARS]})
        if len(results) >= limit:
            break
    return results or None


async def run_web_search(
    query: str, *, limit: int = SEARCH_RESULT_LIMIT, kind: str = "web"
) -> tuple[list[dict[str, str]], str]:
    """The actual search logic behind ``web.search``, independent of the tool-call plumbing
    (``ToolExecutionRequest``/``Context``) — so non-agent callers (e.g. the market read pipeline)
    can reuse the exact same search/allowlist path without faking a tool-call context.

    ``kind="news"`` prefers Brave's news endpoint (real dated articles) when BRAVE_API_KEY is set;
    ``kind="web"`` (default) prefers Brave's general web search, then Exa, then DuckDuckGo.
    """
    limit = max(1, min(limit, SEARCH_RESULT_LIMIT))
    news = kind == "news"

    brave_results = await asyncio.to_thread(_search_via_brave, query, limit=limit, news=news)
    if brave_results is not None:
        results, source = brave_results, "brave_news" if news else "brave_web"
    else:
        exa_results = None if news else await asyncio.to_thread(_search_via_exa, query, limit=limit)
        if exa_results is not None:
            results, source = exa_results, "exa"
        else:
            try:
                html_text = await asyncio.to_thread(_http_get_text, _SEARCH_ENDPOINT, data={"q": query})
            except error.HTTPError as exc:
                raise RuntimeError(f"web search failed: HTTP {exc.code}") from exc
            except error.URLError as exc:
                raise RuntimeError(f"web search failed: {exc.reason}") from exc
            results, source = _parse_search_results(html_text, limit=limit), "duckduckgo"

    allowlist = _fetch_allowlist()
    if allowlist:
        results = [r for r in results if _host_allowed(parse.urlparse(r["url"]).hostname or "", allowlist)]
    return results, source


async def search_web(request: ToolExecutionRequest, context: ToolExecutionContext) -> ToolExecutionResult:
    query = str(request.arguments.get("query") or "").strip()
    if not query:
        raise ValueError("query is required")
    raw_limit = request.arguments.get("limit")
    try:
        limit = int(raw_limit) if raw_limit is not None else SEARCH_RESULT_LIMIT
    except (TypeError, ValueError):
        limit = SEARCH_RESULT_LIMIT

    results, source = await run_web_search(query, limit=limit)
    if not results:
        return ToolExecutionResult(
            tool_id=request.tool_id,
            ok=True,
            summary=f"No web results for '{query}'",
            output={"query": query, "results": [], "source": source},
        )
    summary = f"{len(results)} web result{'s' if len(results) != 1 else ''} for '{query}' — top: {results[0]['title']}"
    return ToolExecutionResult(
        tool_id=request.tool_id,
        ok=True,
        summary=summary,
        output={"query": query, "results": results, "source": source},
    )


async def fetch_web(request: ToolExecutionRequest, context: ToolExecutionContext) -> ToolExecutionResult:
    url = str(request.arguments.get("url") or "").strip()
    if not url:
        raise ValueError("url is required")
    allowlist = _fetch_allowlist()
    if allowlist:
        hostname = parse.urlparse(url if "://" in url else f"https://{url}").hostname or ""
        if not _host_allowed(hostname, allowlist):
            raise RuntimeError(
                f"'{hostname}' is not in the configured fetch allowlist ({_FETCH_ALLOWLIST_ENV})"
            )
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
