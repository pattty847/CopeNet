from __future__ import annotations

import html
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any
from urllib import error, request


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
