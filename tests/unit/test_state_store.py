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
