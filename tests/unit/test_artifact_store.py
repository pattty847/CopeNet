from copenet.core.runtime import ArtifactStore


def test_artifact_store_create_list_and_get(tmp_dir) -> None:
    store = ArtifactStore(root_dir=tmp_dir / "artifacts")

    created = store.create(
        session_key="alpha",
        run_id="run-1",
        artifact_type="summary",
        title="Summary 1",
        body="A compact answer.",
        source_asset_ids=["asset-1"],
        metadata={"provider": "prompted"},
    )

    listed = store.list_for_session("alpha")
    assert len(listed) == 1
    assert listed[0].artifact_id == created.artifact_id
    assert listed[0].source_asset_ids == ["asset-1"]
    assert listed[0].metadata["provider"] == "prompted"

    loaded = store.get("alpha", created.artifact_id)
    assert loaded is not None
    assert loaded.title == "Summary 1"
    assert loaded.body == "A compact answer."
