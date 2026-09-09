"""The Home desk snapshot: what ran lately, and health counted rather than sampled."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from copenet.core.home.desk import build_desk_snapshot
from copenet.core.home.focus import FocusStore
from copenet.core.home.quotes import ATTRIBUTED, QUOTES, quote_for
from copenet.core.runtime.runs import RunRecord, RunStore

NOW = datetime(2026, 9, 9, 15, 0, tzinfo=timezone.utc)


def make_run(
    *,
    run_id: str,
    session_key: str = "s1",
    minutes_ago: float = 5,
    duration_s: float | None = 2,
    tool_steps: int = 0,
    status: str = "ok",
    error: str | None = None,
    user_message: str = "do the thing",
) -> RunRecord:
    started = NOW - timedelta(minutes=minutes_ago)
    completed = started + timedelta(seconds=duration_s) if duration_s is not None else None
    return RunRecord(
        run_id=run_id,
        session_key=session_key,
        provider="openai-codex",
        model="gpt-5.5",
        status=status,
        user_message=user_message,
        tool_execution_mode="native",
        will_attempt_tool_loop=True,
        started_at=started.isoformat(),
        completed_at=completed.isoformat() if completed else None,
        working_set={},
        tool_steps=[{"toolId": "files.rg"} for _ in range(tool_steps)],
        error=error,
    )


def snapshot(runs, **kwargs):
    defaults = dict(session_titles={"s1": "Chart research"}, total_sessions=592, in_flight=0, quote=None, now=NOW)
    defaults.update(kwargs)
    return build_desk_snapshot(runs=runs, **defaults)


def test_health_counts_tool_calls_and_errors_inside_the_hour_window():
    health = snapshot(
        [
            make_run(run_id="r1", minutes_ago=5, tool_steps=3),
            make_run(run_id="r2", minutes_ago=50, tool_steps=2, status="error", error="boom"),
            # Outside the window: counted by nothing.
            make_run(run_id="r3", minutes_ago=200, tool_steps=99),
        ]
    ).health

    assert health.runs == 2
    assert health.tool_calls == 5
    assert health.error_rate == pytest.approx(0.5)


def test_average_latency_is_absent_rather_than_zero_when_nothing_completed():
    health = snapshot([make_run(run_id="r1", duration_s=None)]).health

    assert health.avg_latency_ms is None


def test_average_latency_ignores_runs_that_never_completed():
    health = snapshot(
        [
            make_run(run_id="r1", duration_s=4),
            make_run(run_id="r2", duration_s=6),
            make_run(run_id="r3", duration_s=None),
        ]
    ).health

    assert health.avg_latency_ms == 5_000


def test_active_sessions_means_sessions_that_ran_today_not_the_filing_cabinet():
    health = snapshot(
        [
            make_run(run_id="r1", session_key="s1", minutes_ago=30),
            make_run(run_id="r2", session_key="s1", minutes_ago=90),
            make_run(run_id="r3", session_key="s2", minutes_ago=600),
            # Three days old: the session exists, but it is not active.
            make_run(run_id="r4", session_key="s3", minutes_ago=60 * 72),
        ]
    ).health

    assert health.active_sessions == 2
    assert health.total_sessions == 592


def test_activity_series_bucket_a_burst_into_one_column():
    health = snapshot([make_run(run_id=f"r{i}", minutes_ago=2, tool_steps=1) for i in range(4)]).health

    assert sum(health.tool_call_series) == 4
    assert max(health.tool_call_series) == 4
    assert len(health.tool_call_series) == 12


def test_activity_rows_carry_the_session_title_and_fall_back_to_the_key():
    activity = snapshot([make_run(run_id="r1", session_key="s1"), make_run(run_id="r2", session_key="unknown")]).activity

    assert activity[0].session_title == "Chart research"
    assert activity[1].session_title == "unknown"


def test_a_run_with_no_message_says_so_rather_than_rendering_blank():
    activity = snapshot([make_run(run_id="r1", user_message="   ")]).activity

    assert activity[0].summary == "(no message)"


def test_activity_is_capped_but_health_still_counts_every_run():
    runs = [make_run(run_id=f"r{i}", minutes_ago=1, tool_steps=1) for i in range(20)]

    result = snapshot(runs, activity_limit=5)

    assert len(result.activity) == 5
    assert result.health.tool_calls == 20


# ------------------------------------------------------------------ cross-session runs


def test_run_store_lists_recent_runs_across_every_session(tmp_path):
    store = RunStore(root_dir=tmp_path / "runs")
    store.create(make_run(run_id="old", session_key="a", minutes_ago=500))
    store.create(make_run(run_id="new", session_key="b", minutes_ago=1))
    store.create(make_run(run_id="middle", session_key="c", minutes_ago=60))

    recent = store.list_recent_across_sessions(limit=10)

    assert [record.run_id for record in recent] == ["new", "middle", "old"]


def test_cross_session_listing_respects_its_limit(tmp_path):
    store = RunStore(root_dir=tmp_path / "runs")
    for index in range(10):
        store.create(make_run(run_id=f"r{index}", session_key=f"s{index}", minutes_ago=index))

    assert len(store.list_recent_across_sessions(limit=4)) == 4


def test_per_session_listing_still_works_after_sharing_the_tail_reader(tmp_path):
    store = RunStore(root_dir=tmp_path / "runs")
    store.create(make_run(run_id="a1", session_key="a"))
    store.create(make_run(run_id="a2", session_key="a"))
    store.create(make_run(run_id="b1", session_key="b"))

    assert [record.run_id for record in store.list_for_session("a")] == ["a1", "a2"]
    assert store.list_for_session("a", limit=0) == []


# ------------------------------------------------------------------------- focus list


def test_focus_round_trips_items_notes_and_quick_launch(tmp_path):
    store = FocusStore(path=tmp_path / "focus.json")

    state = store.add_item("  Check TSLA   chart setup ")
    item_id = state.items[0].item_id
    assert state.items[0].text == "Check TSLA chart setup"

    store.set_item(item_id, done=True)
    store.set_notes("CPI Wednesday")
    store.set_quick_launch(["market_radar", "market_radar", " ", "run_sweep"])

    reloaded = FocusStore(path=tmp_path / "focus.json").load()
    assert reloaded.items[0].done is True
    assert reloaded.notes == "CPI Wednesday"
    # Duplicates and blanks are dropped; order is the operator's.
    assert reloaded.quick_launch == ["market_radar", "run_sweep"]


def test_focus_rejects_blank_text_and_unknown_ids(tmp_path):
    store = FocusStore(path=tmp_path / "focus.json")

    with pytest.raises(ValueError):
        store.add_item("   ")
    with pytest.raises(KeyError):
        store.set_item("nope", done=True)
    with pytest.raises(KeyError):
        store.remove_item("nope")


def test_clear_done_keeps_the_unfinished(tmp_path):
    store = FocusStore(path=tmp_path / "focus.json")
    keep = store.add_item("keep me").items[0].item_id
    drop = store.add_item("drop me").items[-1].item_id
    store.set_item(drop, done=True)

    state = store.clear_done()

    assert [item.item_id for item in state.items] == [keep]


# ----------------------------------------------------------------------------- quotes


def test_the_quote_is_stable_for_a_day_and_moves_the_next():
    day = datetime(2026, 9, 9).date()
    assert quote_for(day) == quote_for(day)
    assert quote_for(day)["text"] != quote_for(day + timedelta(days=1))["text"]


def test_borrowed_lines_are_not_signed_as_copenet():
    """Signing Buffett "— CopeNet" would be a misattribution the card states as fact."""
    for text, attribution in ATTRIBUTED.items():
        assert text in QUOTES, f"ATTRIBUTED names a quote that is no longer in the list: {text!r}"
        assert attribution != "CopeNet"

    signed = {quote_for(datetime(2026, 1, 1).date() + timedelta(days=offset))["text"] for offset in range(len(QUOTES))}
    assert signed == set(QUOTES), "every quote should be reachable by rotation"
