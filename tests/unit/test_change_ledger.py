"""Change ledger: durable record of the agent's own file changes, rendered per turn."""

from __future__ import annotations

from pathlib import Path

from copenet.core.sessions.change_ledger import (
    LEDGER_HEADER,
    LEDGER_MAX_FILES,
    ChangeLedgerStore,
    append_change_ledger,
    content_digest,
    file_states,
    last_digests,
    render_change_ledger,
)


def _store(tmp_path: Path) -> ChangeLedgerStore:
    return ChangeLedgerStore(root_dir=tmp_path / "ledger")


def _write(workspace: Path, rel: str, text: str) -> str:
    target = workspace / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return content_digest(text)


def test_records_are_appended_per_session_and_read_back_in_order(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.record(session_key="s1", run_id="r1", path="a.py", action="edited", lines_added=2, lines_removed=1, digest_before="0", digest_after="1")
    store.record(session_key="s1", run_id="r2", path="b.py", action="created", lines_added=10, lines_removed=0, digest_before=None, digest_after="2")
    store.record(session_key="other", run_id="r9", path="z.py", action="edited", lines_added=1, lines_removed=1, digest_before="8", digest_after="9")

    rows = store.entries("s1")
    assert [(row.path, row.action, row.run_id) for row in rows] == [("a.py", "edited", "r1"), ("b.py", "created", "r2")]
    assert store.entries("missing") == []
    assert last_digests(rows) == {"a.py": "1", "b.py": "2"}


def test_render_reports_unchanged_changed_and_missing_files(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    kept = _write(workspace, "kept.py", "x = 1\n")
    drifted = _write(workspace, "drifted.py", "y = 1\n")
    store = _store(tmp_path)
    store.record(session_key="s", run_id="r1", path="kept.py", action="edited", lines_added=1, lines_removed=0, digest_before="0", digest_after=kept)
    store.record(session_key="s", run_id="r1", path="drifted.py", action="created", lines_added=1, lines_removed=0, digest_before=None, digest_after=drifted)
    store.record(session_key="s", run_id="r2", path="gone.py", action="created", lines_added=3, lines_removed=0, digest_before=None, digest_after="deadbeefdeadbeef")
    # operator (or anything else) changes a file between turns
    (workspace / "drifted.py").write_text("y = 2\n", encoding="utf-8")

    text, counts = render_change_ledger(store.entries("s"), workspace)

    assert text.startswith(LEDGER_HEADER)
    assert "- gone.py: created (turn 2, +3/−0); now MISSING from disk" in text
    assert f"- kept.py: edited (turn 1, +1/−0); on disk as you left it (digest {kept})" in text
    assert "- drifted.py: created (turn 1, +1/−0); CHANGED ON DISK since your last edit" in text
    assert "read it again before editing" in text
    assert counts == {"fileCount": 3, "changedOnDisk": 1, "missing": 1}
    # newest-touched first
    assert text.index("gone.py") < text.index("kept.py")


def test_repeated_edits_fold_into_one_line_with_turn_range(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    final = _write(workspace, "app.py", "v3\n")
    store = _store(tmp_path)
    store.record(session_key="s", run_id="r1", path="app.py", action="created", lines_added=5, lines_removed=0, digest_before=None, digest_after="a")
    store.record(session_key="s", run_id="r2", path="app.py", action="edited", lines_added=2, lines_removed=1, digest_before="a", digest_after="b")
    store.record(session_key="s", run_id="r3", path="app.py", action="edited", lines_added=0, lines_removed=3, digest_before="b", digest_after=final)

    states = file_states(store.entries("s"), workspace)
    assert len(states) == 1
    assert (states[0].edit_count, states[0].first_turn, states[0].last_turn) == (3, 1, 3)
    assert (states[0].lines_added, states[0].lines_removed, states[0].created, states[0].on_disk) == (7, 4, True, "unchanged")
    text, _ = render_change_ledger(store.entries("s"), workspace)
    assert "- app.py: created, then edited 3× (turns 1–3, +7/−4)" in text


def test_empty_ledger_adds_nothing_to_the_message(tmp_path: Path) -> None:
    text, counts = render_change_ledger([], tmp_path)
    assert text == "" and counts["fileCount"] == 0
    assert append_change_ledger("hello", text) == "hello"
    assert append_change_ledger("hello", "LEDGER") == "hello\n\nLEDGER"


def test_ledger_is_capped_and_summarizes_the_rest(tmp_path: Path) -> None:
    store = _store(tmp_path)
    for index in range(LEDGER_MAX_FILES + 5):
        store.record(session_key="s", run_id=f"r{index}", path=f"f{index:03d}.py", action="created", lines_added=1, lines_removed=0, digest_before=None, digest_after="x")
    text, counts = render_change_ledger(store.entries("s"), tmp_path)
    assert counts["fileCount"] == LEDGER_MAX_FILES + 5
    assert text.count("\n- ") == LEDGER_MAX_FILES + 1
    assert "and 5 more files changed earlier this session" in text
