"""Declared preview shapes for current tool results."""

from typing import Callable


def preview_plan(body: dict) -> dict | None:
    items = body.get("items")
    if isinstance(items, list):
        clean = [
            {"content": str(i.get("content") or ""), "status": str(i.get("status") or "pending")}
            for i in items
            if isinstance(i, dict) and i.get("content")
        ]
        if clean:
            return {"type": "plan", "items": clean}
    return None


def preview_web_search(body: dict) -> dict | None:
    results = body.get("results")
    if isinstance(results, list):
        clean = [
            {
                "title": str(r.get("title") or ""),
                "url": str(r.get("url") or ""),
                "snippet": str(r.get("snippet") or ""),
            }
            for r in results
            if isinstance(r, dict) and r.get("url")
        ]
        return {"type": "web_search", "query": str(body.get("query") or ""), "results": clean[:8]}
    return None


def preview_web_document(body: dict) -> dict | None:
    text = body.get("text")
    if isinstance(text, str):
        return {
            "type": "web_doc",
            "url": str(body.get("url") or ""),
            "title": str(body.get("title") or ""),
            "wordCount": int(body.get("wordCount") or 0),
            "text": text.rstrip()[:600],
        }
    return None


def preview_file_read(body: dict) -> dict | None:
    path = body.get("path")
    content = body.get("content")
    if isinstance(path, str) and isinstance(content, str):
        preview_content = content.rstrip()[:24000]
        lines = preview_content.split("\n")
        return {
            "type": "file_read",
            "path": path,
            "lines": lines,
            "startLine": body.get("startLine", 1),
            "totalLines": len(lines),
        }
    return None


def preview_repo_search(body: dict) -> dict | None:
    matches = body.get("matches")
    if isinstance(matches, list):
        return {
            "type": "repo_search",
            "query": str(body.get("pattern") or body.get("query") or ""),
            "matches": [
                {
                    "path": str(row.get("path") or ""),
                    "line": int(row.get("line") or 0),
                    "snippet": str(row.get("text") or ""),
                }
                for row in matches
                if isinstance(row, dict)
            ],
            "totalMatches": body.get("totalMatches"),
        }
    return None


def preview_shell(body: dict) -> dict | None:
    stdout = body.get("stdout")
    stderr = body.get("stderr")
    if isinstance(stdout, str) or isinstance(stderr, str):
        command = str(body.get("command") or "")
        streams = [str(stdout or "").rstrip(), str(stderr or "").rstrip()]
        text = "\n".join((part for part in streams if part))
        return {
            "type": "raw",
            "text": f"$ {command}\n{text}" if command else text,
            "fullChars": len(f"$ {command}\n{text}" if command else text),
        }
    return None


def preview_diff(body: dict) -> dict | None:
    diff = body.get("diff")
    if isinstance(diff, str) and diff.strip():
        return {
            "type": "diff",
            "path": str(body.get("path") or body.get("target") or ""),
            "diff": diff,
            "linesAdded": int(body.get("linesAdded") or 0),
            "linesRemoved": int(body.get("linesRemoved") or 0),
            "truncated": bool(body.get("diffTruncated")),
            "created": bool(body.get("created")),
            "afterDigest": str(body.get("digest") or ""),
        }
    return None


PREVIEW_BUILDERS: dict[str, Callable[[dict], dict | None]] = {
    "plan.write": preview_plan,
    "web.search": preview_web_search,
    "web.fetch": preview_web_document,
    "files.read": preview_file_read,
    "files.rg": preview_repo_search,
    "shell.exec": preview_shell,
    "files.write": preview_diff,
    "files.edit": preview_diff,
}
