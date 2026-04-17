from copenet.core.orchestrator.working_set import assemble_working_set
from copenet.core.runtime import ArtifactStore
from copenet.core.sessions import SessionStateRecord


def test_working_set_uses_recent_transcript_window_and_artifacts(tmp_dir) -> None:
    artifact_store = ArtifactStore(root_dir=tmp_dir / "artifacts")
    artifact = artifact_store.create(
        session_key="alpha",
        run_id="run-1",
        artifact_type="summary",
        title="Auth module summary",
        body="Auth is implemented in auth.py.",
    )
    transcript = [
        {"role": "user", "content": f"older-{index}"}
        for index in range(10)
    ]
    state = SessionStateRecord(
        session_key="alpha",
        task_summary="Investigate auth",
        relevant_artifact_ids=[artifact.artifact_id],
        relevant_asset_ids=["asset-1"],
    )

    package = assemble_working_set(
        user_message="Find the auth flow.",
        session_state=state,
        transcript_window=transcript,
        artifact_store=artifact_store,
        system_prompt="Be helpful.",
        session_key="alpha",
    )

    assert "Auth module summary" in package.prompt
    assert "older-9" in package.prompt
    assert "older-0" not in package.prompt
    assert package.metadata["artifactIds"] == [artifact.artifact_id]
    assert package.metadata["assetIds"] == ["asset-1"]
