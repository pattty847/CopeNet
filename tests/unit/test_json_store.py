from __future__ import annotations

import json
from pathlib import Path

from copenet.core._json_store import append_jsonl, read_json, write_json_atomic


def test_read_json_returns_fallback_for_missing_or_invalid_file(tmp_path: Path) -> None:
    missing = tmp_path / "missing.json"
    assert read_json(missing, {"ok": False}) == {"ok": False}

    broken = tmp_path / "broken.json"
    broken.write_text("{not-json", encoding="utf-8")
    assert read_json(broken, []) == []


def test_write_json_atomic_writes_indented_json_and_removes_temp_file(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "store.json"

    write_json_atomic(target, {"items": [{"id": "one"}]})

    assert json.loads(target.read_text(encoding="utf-8")) == {"items": [{"id": "one"}]}
    assert target.read_text(encoding="utf-8").endswith("\n")
    assert not target.with_suffix(".tmp").exists()


def test_write_json_atomic_can_preserve_no_trailing_newline_shape(tmp_path: Path) -> None:
    target = tmp_path / "store.json"

    write_json_atomic(target, {"routes": []}, trailing_newline=False)

    assert target.read_text(encoding="utf-8").endswith("}") is True
    assert not target.read_text(encoding="utf-8").endswith("\n")


def test_append_jsonl_adds_one_json_object_per_line(tmp_path: Path) -> None:
    target = tmp_path / "events" / "changelog.jsonl"

    append_jsonl(target, {"id": "a"})
    append_jsonl(target, {"id": "b"})

    rows = [json.loads(line) for line in target.read_text(encoding="utf-8").splitlines()]
    assert rows == [{"id": "a"}, {"id": "b"}]
