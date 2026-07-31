from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path

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


def test_two_session_store_instances_preserve_concurrent_creates(tmp_dir) -> None:
    path = tmp_dir / "index.json"
    stores = [SessionStore(path=path), SessionStore(path=path)]

    def create_range(store: SessionStore, prefix: str) -> None:
        for index in range(20):
            store.create_session(session_key=f"{prefix}-{index}", provider="fake")

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(create_range, stores[0], "left"),
            executor.submit(create_range, stores[1], "right"),
        ]
        for future in futures:
            future.result()

    keys = {entry.session_key for entry in stores[0].list_sessions()}
    assert keys == {
        *(f"left-{index}" for index in range(20)),
        *(f"right-{index}" for index in range(20)),
    }


def test_interrupted_session_index_replace_preserves_last_good_file_and_can_retry(
    tmp_dir, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = SessionStore(path=tmp_dir / "index.json")
    store.create_session(session_key="alpha", provider="fake")
    original_replace = Path.replace
    failed_once = False

    def interrupt_index_replace(source: Path, target: Path) -> Path:
        nonlocal failed_once
        if source == store.path.with_suffix(".json.tmp") and not failed_once:
            failed_once = True
            raise OSError("simulated interrupted atomic replacement")
        return original_replace(source, target)

    monkeypatch.setattr(Path, "replace", interrupt_index_replace)
    with pytest.raises(OSError, match="simulated interrupted atomic replacement"):
        store.create_session(session_key="beta", provider="fake")

    payload = json.loads(store.path.read_text(encoding="utf-8"))
    assert [item["session_key"] for item in payload["sessions"]] == ["alpha"]

    created = store.create_session(session_key="beta", provider="fake")
    assert created.session_key == "beta"
    assert {entry.session_key for entry in store.list_sessions()} == {"alpha", "beta"}


@pytest.mark.parametrize("unsafe_key", ["a/b", "a b", "a:b", "a\\b", "a?b"])
def test_create_session_rejects_keys_unsafe_for_durable_storage(
    session_store: SessionStore, unsafe_key: str
) -> None:
    # Confirmed audit finding (C-A-003): the runs/artifacts/state stores each turn a
    # session_key into a filename by deleting unsafe characters, so an accepted key like
    # "a/b" and an unrelated "ab" session would silently share one runs/artifacts/state
    # file. Reject anything that isn't already sanitizer-stable at creation time.
    with pytest.raises(ValueError, match="unsafe for durable storage"):
        session_store.create_session(session_key=unsafe_key, provider="fake")


def test_create_session_accepts_keys_stable_under_the_durable_store_sanitizer(
    session_store: SessionStore,
) -> None:
    created = session_store.create_session(session_key="alpha-2.beta_3", provider="fake")
    assert session_store.get(created.session_key) is not None


def test_assert_session_binding_raises_for_locked_field_mismatches(session_store: SessionStore) -> None:
    # Provider and profile stay locked after first use; model and Access do not.
    session_store.create_session(
        session_key="alpha",
        provider="fake",
        model="model-a",
        system_prompt_id="default",
        task_prompt_id="none",
    )

    with pytest.raises(RuntimeError, match="locked to provider"):
        session_store.assert_session_binding("alpha", provider="other", model="model-a")
    with pytest.raises(RuntimeError, match="locked to profile"):
        session_store.assert_session_binding("alpha", provider="fake", model="model-a", system_prompt_id="other")


def test_assert_session_binding_reconciles_model_and_access_mid_session(session_store: SessionStore) -> None:
    # Mid-session runtime mutability (A + B1): a same-provider model switch and an
    # Access change update the stored binding instead of raising.
    session_store.create_session(
        session_key="alpha",
        provider="fake",
        model="model-a",
        system_prompt_id="default",
        task_prompt_id="none",
    )

    switched = session_store.assert_session_binding(
        "alpha", provider="fake", model="model-b", system_prompt_id="default", task_prompt_id="full-access"
    )
    assert switched.model == "model-b"
    assert switched.task_prompt_id == "full-access"

    # The change persisted to the stored entry, not just the returned object.
    reloaded = session_store.get("alpha")
    assert reloaded is not None
    assert reloaded.model == "model-b"
    assert reloaded.task_prompt_id == "full-access"

    # A request with no model must never clear a stored model.
    kept = session_store.assert_session_binding(
        "alpha", provider="fake", model=None, system_prompt_id="default", task_prompt_id="full-access"
    )
    assert kept.model == "model-b"


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


def test_minimal_legacy_session_entry_uses_backward_compatible_defaults(tmp_dir) -> None:
    store = SessionStore(path=tmp_dir / "index.json")
    store.path.write_text(
        json.dumps({"sessions": [{"session_key": "legacy", "provider": "fake"}]}),
        encoding="utf-8",
    )

    entry = store.get("legacy")
    assert entry is not None
    assert entry.session_id == "legacy"
    assert entry.session_type == "standard"
    assert entry.archived is False
    assert entry.model is None
    assert entry.in_flight_run_id is None


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


@pytest.mark.parametrize(
    ("stored_access", "requested_access", "expected_access"),
    [
        pytest.param(None, "full-access", "full-access", id="default-to-full-access"),
        pytest.param(None, None, None, id="default-continuation"),
        pytest.param("full-access", None, None, id="full-access-to-default"),
    ],
)
def test_session_access_reconciles_to_operator_requested_mode(
    session_store: SessionStore,
    stored_access: str | None,
    requested_access: str | None,
    expected_access: str | None,
) -> None:
    # Access is operator-driven and reconciles mid-session. A model can never escalate
    # itself — it doesn't supply task_prompt_id — and Full Access stays provider-gated
    # downstream in policy_for_task_mode, so this reconcile can't silently over-grant.
    session_store.create_session(
        session_key="access-transition",
        provider="fake",
        task_prompt_id=stored_access,
    )
    entry = session_store.assert_session_binding(
        session_key="access-transition",
        provider="fake",
        task_prompt_id=requested_access,
    )
    assert entry.task_prompt_id == expected_access
