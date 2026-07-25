"""Regression coverage for the corrupt-store data-loss fix.

Confirmed audit finding (2026-07-24, C-A-007): read_json used to treat a
corrupt file identically to a missing one, so a corrupted MemoryStore/AppStore
loaded as empty and the next save silently overwrote the still-recoverable
original content with only the new item. See docs/audit/.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from copenet.core._json_store import JsonStoreError
from copenet.core.memory.store import MemoryRecord, MemoryStore


def test_upsert_refuses_to_clobber_a_corrupted_store(tmp_path: Path) -> None:
    path = tmp_path / "memory.json"
    store = MemoryStore(path)
    store.upsert(MemoryRecord(id="m-1", category="fact", title="Original", summary="Original memory"))

    # Corrupt the file on disk, as if it had been truncated by a crash mid-write.
    path.write_text("{not-json", encoding="utf-8")

    # The old behavior silently treated this as an empty store, and the upsert below
    # would have overwritten the file with only "m-2" — destroying "m-1" forever.
    with pytest.raises(JsonStoreError):
        store.upsert(MemoryRecord(id="m-2", category="fact", title="New", summary="New memory"))

    # The old behavior would have overwritten the corrupt file with a fresh
    # single-item store, silently destroying "m-1". The fix must leave the corrupt
    # bytes untouched (no clobbering write happens) and quarantine a forensic copy.
    assert path.read_text(encoding="utf-8") == "{not-json"
    backup = path.with_suffix(".json.corrupt")
    assert backup.exists()
    assert backup.read_text(encoding="utf-8") == "{not-json"
