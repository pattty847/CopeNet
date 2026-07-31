from concurrent.futures import ThreadPoolExecutor
import json

from copenet.core.runtime import RunRecord, RunStore


def _record(run_id: str, session_key: str = "alpha") -> RunRecord:
    return RunRecord(
        run_id=run_id,
        session_key=session_key,
        provider="fake",
        model="model-a",
        status="ok",
        user_message=run_id,
        tool_execution_mode="none",
        will_attempt_tool_loop=False,
    )


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


def test_run_store_ignores_truncated_final_jsonl_record(tmp_dir) -> None:
    store = RunStore(root_dir=tmp_dir / "runs")
    path = store.runs_path_for("alpha")
    path.write_text(json.dumps(_record("run-1").to_json()) + '\n{"run_id":"partial', encoding="utf-8")

    records = store.list_for_session("alpha")
    assert [record.run_id for record in records] == ["run-1"]


def test_two_run_store_instances_append_without_loss_and_preserve_writer_order(tmp_dir) -> None:
    root = tmp_dir / "runs"
    stores = [RunStore(root_dir=root), RunStore(root_dir=root)]

    def append_series(store: RunStore, prefix: str) -> None:
        for index in range(20):
            store.create(_record(f"{prefix}-{index}"))

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(append_series, stores[0], "left"),
            executor.submit(append_series, stores[1], "right"),
        ]
        for future in futures:
            future.result()

    run_ids = [record.run_id for record in stores[0].list_for_session("alpha", limit=100)]
    assert len(run_ids) == 40
    assert len(set(run_ids)) == 40
    assert [run_id for run_id in run_ids if run_id.startswith("left-")] == [f"left-{index}" for index in range(20)]
    assert [run_id for run_id in run_ids if run_id.startswith("right-")] == [
        f"right-{index}" for index in range(20)
    ]


def test_minimal_legacy_run_record_uses_backward_compatible_defaults(tmp_dir) -> None:
    store = RunStore(root_dir=tmp_dir / "runs")
    path = store.runs_path_for("alpha")
    path.write_text(
        json.dumps({"run_id": "legacy", "session_key": "alpha", "provider": "fake", "status": "ok"}) + "\n",
        encoding="utf-8",
    )

    record = store.get("alpha", "legacy")
    assert record is not None
    assert record.tool_execution_mode == "none"
    assert record.transition_reason == "start_turn"
    assert record.tool_steps == []
    assert record.artifact_ids == []
    assert record.message_count == 0
