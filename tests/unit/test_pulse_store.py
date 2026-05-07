import json

from copenet.core.pulse import PulseRecord, PulseStore


def test_pulse_store_creates_lists_and_updates_records(tmp_dir) -> None:
    store = PulseStore(path=tmp_dir / "pulses.json")

    created = store.create(
        PulseRecord(
            pulse_id="pulse-1",
            status="new",
            title="Follow up on provider drift",
            summary="Recent sessions suggest the provider contract may be drifting.",
            why_now="A merged follow-up would help compare the outcomes.",
            source_session_keys=["alpha"],
            source_run_ids=["run-1"],
            created_at="2026-05-07T00:00:00+00:00",
            updated_at="2026-05-07T00:00:00+00:00",
        )
    )

    loaded = store.get("pulse-1")
    assert loaded is not None
    assert loaded.title == "Follow up on provider drift"
    assert loaded.source_session_keys == ["alpha"]
    assert created.updated_at

    updated = store.save(
        PulseRecord(
            pulse_id="pulse-1",
            status="saved",
            title=loaded.title,
            summary=loaded.summary,
            why_now=loaded.why_now,
            source_session_keys=loaded.source_session_keys,
            source_run_ids=loaded.source_run_ids,
            created_at=loaded.created_at,
            updated_at=loaded.updated_at,
            saved_at="2026-05-07T00:10:00+00:00",
            dismissed_at=None,
        )
    )
    assert updated.status == "saved"
    assert updated.saved_at == "2026-05-07T00:10:00+00:00"

    listing = store.list()
    assert [item.pulse_id for item in listing] == ["pulse-1"]

    payload = json.loads((tmp_dir / "pulses.json").read_text(encoding="utf-8"))
    assert payload["pulses"][0]["pulse_id"] == "pulse-1"
    assert payload["pulses"][0]["status"] == "saved"
