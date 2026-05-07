import json

from copenet.core.sessions import SessionStateRecord, SessionStateStore


def test_session_state_store_creates_and_roundtrips(tmp_dir) -> None:
    store = SessionStateStore(root_dir=tmp_dir / "state")

    created = store.get_or_create("alpha")
    assert created.session_key == "alpha"
    assert created.task_summary is None

    saved = store.save(
        SessionStateRecord(
            session_key="alpha",
            task_summary="Inspect archive restore flow",
            active_entities=["files.list"],
            relevant_artifact_ids=["artifact-1"],
        )
    )
    loaded = store.get("alpha")

    assert loaded is not None
    assert loaded.task_summary == "Inspect archive restore flow"
    assert loaded.active_entities == ["files.list"]
    assert loaded.relevant_artifact_ids == ["artifact-1"]

    payload = json.loads((tmp_dir / "state" / "alpha.json").read_text(encoding="utf-8"))
    assert payload["session_key"] == "alpha"
    assert payload["task_summary"] == "Inspect archive restore flow"
    assert payload["relevant_artifact_ids"] == ["artifact-1"]
    assert saved.updated_at


def test_session_state_store_roundtrips_merge_state(tmp_dir) -> None:
    store = SessionStateStore(root_dir=tmp_dir / "state")

    store.save(
        SessionStateRecord(
            session_key="merged-alpha-beta",
            merge_state={
                "status": "running",
                "total_sources": 2,
                "completed_sources": 1,
                "source_session_keys": ["alpha", "beta"],
                "sources": [
                    {"session_key": "alpha", "title": "Alpha", "status": "complete", "summary": "Alpha summary"},
                    {"session_key": "beta", "title": "Beta", "status": "running", "summary": None},
                ],
            },
        )
    )

    loaded = store.get("merged-alpha-beta")
    assert loaded is not None
    assert loaded.merge_state is not None
    assert loaded.merge_state["status"] == "running"
    assert loaded.merge_state["completed_sources"] == 1
    assert loaded.merge_state["source_session_keys"] == ["alpha", "beta"]


def test_session_state_store_roundtrips_personal_history_fields(tmp_dir) -> None:
    store = SessionStateStore(root_dir=tmp_dir / "state")

    store.save(
        SessionStateRecord(
            session_key="personal-alpha",
            task_summary="Figure out the next step for the launch",
            goals=["Prepare a narrow launch plan"],
            unresolved_questions=["What can ship this week?"],
            prior_decisions=["Keep the scope to one page."],
            starter_intent="plan_my_next_steps",
            topical_tags=["planning", "execution"],
        )
    )

    loaded = store.get("personal-alpha")
    assert loaded is not None
    assert loaded.starter_intent == "plan_my_next_steps"
    assert loaded.topical_tags == ["planning", "execution"]
    assert loaded.prior_decisions == ["Keep the scope to one page."]
