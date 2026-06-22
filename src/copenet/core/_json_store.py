"""Small JSON file helpers for CopeNet's local stores."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def read_json(path: Path, fallback: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return fallback


def write_json_atomic(path: Path, payload: Any, *, trailing_newline: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    body = json.dumps(payload, ensure_ascii=False, indent=2)
    if trailing_newline:
        body += "\n"
    tmp.write_text(body, encoding="utf-8")
    tmp.replace(path)


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
