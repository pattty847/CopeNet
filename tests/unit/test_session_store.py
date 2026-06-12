import json

import pytest

from copenet.core.sessions import SessionStore


def test_create_session_roundtrips_with_snake_case_disk_format(session_store: SessionStore) -> None:
    created = session_store.create_session(
        session_key="alpha",
        provider="fake",
        model="model-a",
        title="Alpha",
        system_prompt_id="default",
        task_prompt_id="none",
    )

    loaded = session_store.get("alpha")
    assert loaded is not None
    assert loaded.session_id == created.session_id
    assert loaded.provider == "fake"

    payload = json.loads(session_store.path.read_text(encoding="utf-8"))
    stored = payload["sessions"][0]
    assert set(stored) >= {
        "session_id",
        "session_key",
        "provider",
        "model",
        "system_prompt_id",
        "task_prompt_id",
        "created_at",
        "updated_at",
    }
    assert "sessionId" not in stored
    assert "providerSessionId" not in stored


def test_get_returns_none_for_unknown_key(session_store: SessionStore) -> None:
    assert session_store.get("missing") is None


def test_create_session_raises_on_duplicate_key(session_store: SessionStore) -> None:
    session_store.create_session(session_key="alpha", provider="fake")
    with pytest.raises(ValueError, match="session already exists"):
        session_store.create_session(session_key="alpha", provider="fake")


def test_assert_session_binding_raises_for_mismatches(session_store: SessionStore) -> None:
    session_store.create_session(
        session_key="alpha",
        provider="fake",
        model="model-a",
        system_prompt_id="default",
        task_prompt_id="none",
    )

    with pytest.raises(RuntimeError, match="locked to provider"):
        session_store.assert_session_binding("alpha", provider="other", model="model-a")
    with pytest.raises(RuntimeError, match="locked to model"):
        session_store.assert_session_binding("alpha", provider="fake", model="other")
    with pytest.raises(RuntimeError, match="locked to profile"):
        session_store.assert_session_binding("alpha", provider="fake", model="model-a", system_prompt_id="other")
    with pytest.raises(RuntimeError, match="locked to task mode"):
        session_store.assert_session_binding(
            "alpha",
            provider="fake",
            model="model-a",
            system_prompt_id="default",
            task_prompt_id="other",
        )


def test_mark_run_started_and_finished_manage_in_flight_lock(session_store: SessionStore) -> None:
    session_store.create_session(session_key="alpha", provider="fake")

    started = session_store.mark_run_started("alpha", run_id="run-1")
    assert started.in_flight_run_id == "run-1"

    with pytest.raises(RuntimeError, match="session is in flight"):
        session_store.mark_run_started("alpha", run_id="run-2")

    finished = session_store.mark_run_finished("alpha", run_id="run-1")
    assert finished.in_flight_run_id is None


def test_rename_session_preserves_other_fields(session_store: SessionStore) -> None:
    created = session_store.create_session(
        session_key="alpha",
        provider="fake",
        model="model-a",
        system_prompt_id="default",
        task_prompt_id="none",
    )

    renamed = session_store.rename_session("alpha", "Renamed")
    assert renamed.title == "Renamed"
    assert renamed.provider == created.provider
    assert renamed.model == created.model
    assert renamed.system_prompt_id == created.system_prompt_id
    assert renamed.task_prompt_id == created.task_prompt_id


def test_set_archived_and_list_sessions(session_store: SessionStore) -> None:
    session_store.create_session(session_key="alpha", provider="fake")
    session_store.create_session(session_key="beta", provider="fake")
    session_store.set_archived("beta", True)

    visible = [entry.session_key for entry in session_store.list_sessions()]
    archived = [entry.session_key for entry in session_store.list_sessions(include_archived=True)]

    assert visible == ["alpha"]
    assert archived == ["beta", "alpha"] or archived == ["alpha", "beta"]


def test_load_map_ignores_camel_case_storage_entries(tmp_dir) -> None:
    store = SessionStore(path=tmp_dir / "index.json")
    store.path.write_text(
        json.dumps(
            {
                "sessions": [
                    {
                        "sessionKey": "legacy-key",
                        "sessionId": "legacy-id",
                        "provider": "fake",
                        "createdAt": "2024-01-01T00:00:00+00:00",
                        "updatedAt": "2024-01-01T00:00:00+00:00",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    assert store.get("legacy-key") is None


def test_corrupt_index_fails_loud_and_backs_up(tmp_dir) -> None:
    """A corrupt index must raise, not silently load empty (which would let the
    next save atomically overwrite the real index with an empty one)."""
    from copenet.core.sessions.session_store import SessionIndexError

    store = SessionStore(path=tmp_dir / "index.json")
    store.path.write_text("{ this is not valid json", encoding="utf-8")

    with pytest.raises(SessionIndexError):
        store.get("anything")

    backup = store.path.with_suffix(store.path.suffix + ".corrupt")
    assert backup.exists(), "corrupt bytes should be preserved for forensics"
    assert backup.read_text(encoding="utf-8") == "{ this is not valid json"


def test_empty_index_file_is_treated_as_no_sessions(tmp_dir) -> None:
    store = SessionStore(path=tmp_dir / "index.json")
    store.path.write_text("", encoding="utf-8")
    assert store.get("anything") is None  # benign, no raise


def test_clear_stale_in_flight_clears_and_reports(session_store: SessionStore) -> None:
    session_store.create_session(session_key="alpha", provider="fake", model="m1")
    session_store.mark_run_started(session_key="alpha", run_id="run-123")

    # Simulate a crash: the marker is on disk and never cleared.
    assert session_store.get("alpha").in_flight_run_id == "run-123"

    stuck = session_store.clear_stale_in_flight()
    assert stuck == [("alpha", "run-123", "fake", "m1")]
    assert session_store.get("alpha").in_flight_run_id is None

    # A second sweep finds nothing and writes nothing new.
    assert session_store.clear_stale_in_flight() == []


def test_clear_stale_in_flight_unblocks_future_sends(session_store: SessionStore) -> None:
    session_store.create_session(session_key="beta", provider="fake")
    session_store.mark_run_started(session_key="beta", run_id="dead-run")

    # Before the sweep, a new run id is rejected as in-flight.
    with pytest.raises(RuntimeError, match="session is in flight"):
        session_store.mark_run_started(session_key="beta", run_id="new-run")

    session_store.clear_stale_in_flight()
    # After the sweep, the session accepts a fresh run again.
    entry = session_store.mark_run_started(session_key="beta", run_id="new-run")
    assert entry.in_flight_run_id == "new-run"
