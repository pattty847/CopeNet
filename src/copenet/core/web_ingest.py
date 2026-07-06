from __future__ import annotations

import html
import os
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any
from urllib import error, request

# Jina Reader (r.jina.ai): free, no-key URL→clean-markdown proxy — this is the primary
# extraction path. Optional JINA_API_KEY raises the rate limit but isn't required; any
# failure (network, rate limit, target error) falls back to the homegrown HTML parser
# below, so a Jina outage degrades quality rather than breaking web.fetch outright.
_JINA_READER_BASE = "https://r.jina.ai/"


class WebIngestError(RuntimeError):
    pass


@dataclass(frozen=True)
class WebExtractResult:
    url: str
    title: str
    text: str
    markdown: str
    excerpt: str
    word_count: int

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "title": self.title,
            "text": self.text,
            "markdown": self.markdown,
            "excerpt": self.excerpt,
            "wordCount": self.word_count,
        }


class _ReadableHtmlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._capture_title = False
        self.title_parts: list[str] = []
        self.blocks: list[str] = []
        self._current: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:  # type: ignore[override]
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "svg", "canvas", "iframe"}:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag == "title":
            self._capture_title = True
            return
        if tag in {"article", "main", "section", "p", "div", "li", "blockquote", "pre", "h1", "h2", "h3", "h4", "h5", "h6", "br", "tr"}:
            self._flush_current()

    def handle_endtag(self, tag: str) -> None:  # type: ignore[override]
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "svg", "canvas", "iframe"}:
            if self._skip_depth:
                self._skip_depth -= 1
            return
        if self._skip_depth:
            return
        if tag == "title":
            self._capture_title = False
            return
        if tag in {"article", "main", "section", "p", "div", "li", "blockquote", "pre", "h1", "h2", "h3", "h4", "h5", "h6", "body", "tr"}:
            self._flush_current()

    def handle_data(self, data: str) -> None:  # type: ignore[override]
        if self._skip_depth:
            return
        cleaned = _normalize_whitespace(data)
        if not cleaned:
            return
        if self._capture_title:
            self.title_parts.append(cleaned)
            return
        self._current.append(cleaned)

    def _flush_current(self) -> None:
        if not self._current:
            return
        text = _normalize_whitespace(" ".join(self._current))
        self._current.clear()
        if text:
            self.blocks.append(text)


def _normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(text or "")).strip()


_JINA_CONTENT_MARKER = "Markdown Content:"


def _parse_jina_reader_response(body: str) -> tuple[str, str]:
    """Split Jina Reader's plain-text envelope (Title:/URL Source:/Warning:/Markdown Content:)
    into (title, content). Raises if the envelope itself reports the TARGET url failed —
    Jina Reader returns HTTP 200 with an embedded warning for a 404 on the real page, so a
    silent success here would otherwise pass a 404 page off as real content."""
    header, _, content = body.partition(_JINA_CONTENT_MARKER)
    title = ""
    warning = ""
    for line in header.splitlines():
        if line.lower().startswith("title:") and not title:
            title = line.split(":", 1)[1].strip()
        elif "warning: target url returned error" in line.lower():
            warning = line.split(":", 1)[1].strip()
    if warning:
        raise WebIngestError(warning)
    return title, content.strip()


def _looks_boilerplate(block: str) -> bool:
    lowered = block.lower()
    if len(lowered) < 24:
        return True
    boilerplate_fragments = (
        "enable javascript",
        "all rights reserved",
        "cookie",
        "privacy policy",
        "terms of service",
        "subscribe",
        "sign up",
        "log in",
        "advertisement",
        "skip to content",
    )
    return any(fragment in lowered for fragment in boilerplate_fragments)


class WebIngestionService:
    def __init__(self, user_agent: str = "CopeNet/0.1 (+https://github.com/pattty847/CopeNet)") -> None:
        self._user_agent = user_agent

    async def extract_url(self, *, url: str, max_chars: int = 20000) -> WebExtractResult:
        raw = (url or "").strip()
        if not raw:
            raise WebIngestError("url is required")
        if not raw.startswith(("http://", "https://")):
            raw = f"https://{raw}"

        try:
            return self._extract_via_jina(raw, max_chars=max_chars)
        except WebIngestError:
            pass  # fall back to the direct fetch below

        req = request.Request(
            raw,
            headers={
                "User-Agent": self._user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,text/plain;q=0.8,*/*;q=0.5",
            },
        )
        try:
            with request.urlopen(req, timeout=20.0) as response:
                content_type = str(response.headers.get("Content-Type") or "")
                charset = response.headers.get_content_charset() or "utf-8"
                body = response.read()
                final_url = str(response.geturl() or raw)
        except error.HTTPError as exc:
            raise WebIngestError(f"web fetch failed: HTTP {exc.code}") from exc
        except error.URLError as exc:
            raise WebIngestError(f"web fetch failed: {exc.reason}") from exc
        except Exception as exc:  # pragma: no cover - safety net
            raise WebIngestError(f"web fetch failed: {exc}") from exc

        if "html" not in content_type and "text/plain" not in content_type:
            raise WebIngestError(f"unsupported content type: {content_type or 'unknown'}")

        text = body.decode(charset, errors="replace")
        if "html" in content_type:
            result = self._extract_from_html(final_url, text, max_chars=max_chars)
        else:
            cleaned = _normalize_whitespace(text)
            result = self._build_result(final_url, final_url, cleaned, max_chars=max_chars)
        return result

    def _extract_via_jina(self, url: str, *, max_chars: int) -> WebExtractResult:
        headers = {"User-Agent": self._user_agent, "Accept": "text/plain"}
        token = os.environ.get("JINA_API_KEY", "").strip()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        req = request.Request(f"{_JINA_READER_BASE}{url}", headers=headers)
        try:
            with request.urlopen(req, timeout=25.0) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                body = response.read().decode(charset, errors="replace")
        except Exception as exc:  # network error, timeout, non-2xx — fall back, don't fail the whole fetch
            raise WebIngestError(f"jina reader failed: {exc}") from exc
        title, text = _parse_jina_reader_response(body)
        if not text.strip():
            raise WebIngestError("jina reader returned no content")
        return self._build_result(url, title or url, text, max_chars=max_chars)

    def _extract_from_html(self, url: str, html_text: str, *, max_chars: int) -> WebExtractResult:
        parser = _ReadableHtmlParser()
        parser.feed(html_text)
        parser.close()
        title = _normalize_whitespace(" ".join(parser.title_parts)) or url
        blocks = [block for block in parser.blocks if not _looks_boilerplate(block)]
        if not blocks:
            blocks = [block for block in parser.blocks if len(block) >= 24]
        joined = "\n\n".join(blocks)
        return self._build_result(url, title, joined, max_chars=max_chars)

    def _build_result(self, url: str, title: str, text: str, *, max_chars: int) -> WebExtractResult:
        normalized = text.strip()
        if not normalized:
            raise WebIngestError("no readable content extracted")
        clipped = normalized[:max_chars].strip()
        excerpt = clipped[:280].strip()
        word_count = len(clipped.split())
        markdown = f"# {title}\n\nSource: {url}\n\n{clipped}\n"
        return WebExtractResult(
            url=url,
            title=title,
            text=clipped,
            markdown=markdown,
            excerpt=excerpt,
            word_count=word_count,
        )
