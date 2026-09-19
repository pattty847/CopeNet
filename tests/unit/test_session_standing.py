"""session.standing — the one line the model leaves, and the facts the row derives."""

from __future__ import annotations

from pathlib import Path

import pytest

from copenet.core.orchestrator.run_state import _carry_standing
from copenet.core.sessions.change_ledger import ChangeLedgerStore
from copenet.core.sessions.session_store import SessionStore
from copenet.core.sessions.state_store import SessionStateRecord, SessionStateStore
from copenet.core.sessions.session_standing import (
    BranchState,
    LedgerSummary,
    common_area,
    find_shared_paths,
    resolve_state,
    summarize_ledger,
)
from copenet.core.sessions.transcript_store import TranscriptStore
from copenet.core.tools import ToolExecutionRequest, ToolPolicy, ToolRegistry
from copenet.core.tools.contracts import ToolExecutionContext


def _ctx(tmp_path: Path, *, run_id: str = "run-1") -> ToolExecutionContext:
    return ToolExecutionContext(
        workdir=tmp_path,
        session_workspace_root=tmp_path,
        session_key="s",
        provider_name="t",
        model="t",
        session_store=SessionStore(path=tmp_path / "i.json"),
        transcript_store=TranscriptStore(root_dir=tmp_path),
        providers={},
        policy=ToolPolicy(allowed_categories={"context"}),
        session_state_store=SessionStateStore(root_dir=tmp_path / "state"),
        run_id=run_id,
    )


# -- the tool -------------------------------------------------------------------


@pytest.mark.asyncio
async def test_standing_note_persists_on_session_state(tmp_path: Path) -> None:
    context = _ctx(tmp_path)
    result = await ToolRegistry().execute(
        ToolExecutionRequest(
            tool_id="session.standing",
            arguments={"note": "fix is in, six tests still red on the fixture shape"},
        ),
        context,
    )
    assert result.ok is True
    record = context.session_state_store.get("s")
    assert record.standing_note == "fix is in, six tests still red on the fixture shape"
    assert record.standing_done is False
    assert record.standing_run_id == "run-1"


@pytest.mark.asyncio
async def test_standing_done_offers_the_thread_for_closing(tmp_path: Path) -> None:
    context = _ctx(tmp_path)
    await ToolRegistry().execute(
        ToolExecutionRequest(
            tool_id="session.standing",
            arguments={"note": "deferred disclosure is live; nothing left open", "done": True},
        ),
        context,
    )
    assert context.session_state_store.get("s").standing_done is True


@pytest.mark.asyncio
async def test_standing_note_is_truncated_to_one_row_title(tmp_path: Path) -> None:
    context = _ctx(tmp_path)
    result = await ToolRegistry().execute(
        ToolExecutionRequest(tool_id="session.standing", arguments={"note": "word " * 80}),
        context,
    )
    assert result.output["truncated"] is True
    assert len(context.session_state_store.get("s").standing_note) <= 120


@pytest.mark.asyncio
async def test_standing_requires_a_note(tmp_path: Path) -> None:
    result = await ToolRegistry().execute(
        ToolExecutionRequest(tool_id="session.standing", arguments={"note": "   "}),
        _ctx(tmp_path),
    )
    assert result.ok is False


def test_standing_is_always_loaded_and_never_deferred() -> None:
    from copenet.core.tools.builtin_readonly import MANIFEST_TOOL_IDS
    from copenet.core.tools.disclosure import ALWAYS_LOADED_TOOL_IDS

    assert "session.standing" in MANIFEST_TOOL_IDS
    assert "session.standing" in ALWAYS_LOADED_TOOL_IDS


# -- expiry ---------------------------------------------------------------------


def test_standing_survives_the_run_that_wrote_it() -> None:
    live = SessionStateRecord(session_key="s", standing_note="tests green", standing_run_id="run-7")
    assert _carry_standing(live, "run-7") == ("tests green", False, "run-7")


def test_standing_expires_when_a_later_run_says_nothing() -> None:
    """A stale line ("six tests still red") is worse than falling back to the title."""
    live = SessionStateRecord(session_key="s", standing_note="six tests still red", standing_run_id="run-7")
    assert _carry_standing(live, "run-8") == (None, False, None)


def test_standing_absent_when_no_live_state() -> None:
    assert _carry_standing(None, "run-1") == (None, False, None)


# -- derived facts --------------------------------------------------------------


def test_ledger_summary_folds_lines_and_names_recent_files(tmp_path: Path) -> None:
    store = ChangeLedgerStore(root_dir=tmp_path)
    for path, added, removed in (
        ("src/copenet/core/market/model_tables.py", 40, 2),
        ("src/copenet/core/market/projection.py", 18, 0),
        ("src/copenet/core/market/model_tables.py", 30, 10),
    ):
        store.record(
            session_key="s",
            run_id="run-1",
            path=path,
            action="edited",
            lines_added=added,
            lines_removed=removed,
            digest_before=None,
            digest_after="abc",
        )
    summary = summarize_ledger(store.entries("s"))
    assert summary.lines_added == 88
    assert summary.lines_removed == 12
    assert summary.file_count == 2
    # Newest touch first, so the row names what was worked on last.
    assert summary.recent_files[0] == "model_tables.py"
    assert summary.area == "src/copenet"


def test_ledger_summary_of_a_thread_that_changed_nothing() -> None:
    summary = summarize_ledger([])
    assert summary.file_count == 0
    assert summary.recent_files == []
    assert summary.area is None


def test_common_area_of_a_top_level_file() -> None:
    assert common_area(["README.md"]) is None
    assert common_area(["docs/PLAN.md"]) == "docs"


def test_state_running_beats_every_other_fact() -> None:
    assert (
        resolve_state(
            in_flight=True,
            approval_command="git clean -fd",
            ledger=LedgerSummary(file_count=3),
            branch=BranchState(branch="feat", commits_ahead=4),
            standing_done=True,
        )
        == "running"
    )


def test_state_blocked_when_policy_asked_for_the_operator() -> None:
    assert (
        resolve_state(
            in_flight=False,
            approval_command="git clean -fd",
            ledger=LedgerSummary(file_count=1),
            branch=BranchState(),
            standing_done=False,
        )
        == "blocked"
    )


def test_state_talk_when_nothing_changed() -> None:
    assert (
        resolve_state(
            in_flight=False,
            approval_command=None,
            ledger=LedgerSummary(),
            branch=BranchState(branch="feat", commits_ahead=2),
            standing_done=False,
        )
        == "talk"
    )


def test_state_unmerged_when_commits_are_waiting() -> None:
    assert (
        resolve_state(
            in_flight=False,
            approval_command=None,
            ledger=LedgerSummary(file_count=2),
            branch=BranchState(branch="claude/x", commits_ahead=4, trunk="main"),
            standing_done=True,
        )
        == "unmerged"
    )


def test_state_done_only_when_the_model_said_so_and_nothing_is_unmerged() -> None:
    merged = BranchState(branch="main", commits_ahead=0, trunk="main")
    assert (
        resolve_state(
            in_flight=False, approval_command=None, ledger=LedgerSummary(file_count=2), branch=merged, standing_done=True
        )
        == "done"
    )
    assert (
        resolve_state(
            in_flight=False, approval_command=None, ledger=LedgerSummary(file_count=2), branch=merged, standing_done=False
        )
        == "idle"
    )


# -- the branch quietly holding two features ------------------------------------


def test_two_sessions_editing_one_file_in_one_workspace_point_at_each_other() -> None:
    ledgers = {
        "a": LedgerSummary(paths=frozenset({"src/HomePage.tsx", "src/a.ts"})),
        "b": LedgerSummary(paths=frozenset({"src/HomePage.tsx", "src/b.ts"})),
    }
    shared = find_shared_paths(ledgers, {"a": "/repo", "b": "/repo"})
    assert shared["a"] == [{"sessionKey": "b", "path": "HomePage.tsx"}]
    assert shared["b"] == [{"sessionKey": "a", "path": "HomePage.tsx"}]


def test_same_file_in_different_workspaces_is_not_a_collision() -> None:
    ledgers = {
        "a": LedgerSummary(paths=frozenset({"src/HomePage.tsx"})),
        "b": LedgerSummary(paths=frozenset({"src/HomePage.tsx"})),
    }
    assert find_shared_paths(ledgers, {"a": "/repo-one", "b": "/repo-two"})["a"] == []


# -- "someone else is working here" ----------------------------------------------


def test_shared_work_notice_names_the_other_thread_and_the_files_that_collide() -> None:
    from copenet.core.sessions.session_standing import SharedWork, append_shared_work, render_shared_work

    text, counts = render_shared_work(
        [
            SharedWork(
                session_key="s2",
                title="Home dashboard rebuild",
                files=["HomePage.tsx", "SectionGrid.tsx"],
                overlapping=["HomePage.tsx"],
            )
        ]
    )
    assert counts == {"sessionCount": 1, "overlapCount": 1}
    assert "Home dashboard rebuild (session s2)" in text
    assert "ALSO EDITED BY YOU: HomePage.tsx" in text
    assert "same branch as theirs" in text
    assert append_shared_work("do the thing", text).startswith("do the thing\n\n")


def test_no_notice_when_no_other_session_is_working_here() -> None:
    from copenet.core.sessions.session_standing import append_shared_work, render_shared_work

    text, counts = render_shared_work([])
    assert text == ""
    assert counts == {"sessionCount": 0, "overlapCount": 0}
    assert append_shared_work("do the thing", text) == "do the thing"


def test_a_thread_with_no_overlap_still_warns_that_the_branch_is_shared() -> None:
    from copenet.core.sessions.session_standing import SharedWork, render_shared_work

    text, counts = render_shared_work(
        [SharedWork(session_key="s3", title="Screener rule windows", files=["evaluate.py"], overlapping=[])]
    )
    assert counts == {"sessionCount": 1, "overlapCount": 0}
    assert "evaluate.py" in text
    assert "ALSO EDITED BY YOU" not in text


def test_a_session_whose_workspace_is_unknown_collides_with_nobody() -> None:
    """An unknown workspace used to fall back to the host's workdir, which credited
    every old benchmark session with whatever branch this checkout was on."""
    ledgers = {
        "a": LedgerSummary(paths=frozenset({"src/HomePage.tsx"})),
        "b": LedgerSummary(paths=frozenset({"src/HomePage.tsx"})),
    }
    assert find_shared_paths(ledgers, {"a": "", "b": ""})["a"] == []
    assert find_shared_paths(ledgers, {"a": "", "b": "/repo"})["b"] == []
