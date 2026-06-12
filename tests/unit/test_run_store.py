from copenet.core.runtime import RunRecord, RunStore


def test_run_store_create_list_and_get(tmp_dir) -> None:
    store = RunStore(root_dir=tmp_dir / "runs")
    created = store.create(
        RunRecord(
            run_id="run-1",
            session_key="alpha",
            provider="prompted",
            model="model-a",
            status="ok",
            user_message="Inspect the repo",
            tool_execution_mode="batch",
            will_attempt_tool_loop=True,
            working_set={"artifactIds": ["artifact-1"]},
            tool_steps=[
                {"toolId": "shell.exec", "ok": True, "summary": "Listed entries", "error": None},
                {"toolId": "files.read", "ok": True, "summary": "Read README", "error": None},
            ],
            artifact_ids=["artifact-1"],
            output_summary="Inspected the repo.",
            transition_reason="tool_followup",
            terminal_reason="completed",
            tool_results=[{"toolId": "files.read", "success": True, "summary": "Read README"}],
            pending_input_count=0,
            oversized_tool_artifact_ids=["artifact-1"],
        )
    )

    listed = store.list_for_session("alpha")
    assert len(listed) == 1
    assert listed[0].run_id == created.run_id
    assert listed[0].tool_steps[0]["toolId"] == "shell.exec"
    assert listed[0].working_set["artifactIds"] == ["artifact-1"]
    assert listed[0].transition_reason == "tool_followup"
    assert listed[0].terminal_reason == "completed"
    assert listed[0].tool_results[0]["toolId"] == "files.read"

    loaded = store.get("alpha", "run-1")
    assert loaded is not None
    assert loaded.output_summary == "Inspected the repo."
    assert loaded.oversized_tool_artifact_ids == ["artifact-1"]
