from concurrent.futures import ThreadPoolExecutor
import json

from copenet.core.sessions import TranscriptMessage, TranscriptStore
from copenet.core.sessions.transcript_store import to_public_message


def _message(run_id: str, content: str) -> TranscriptMessage:
    return TranscriptMessage(
        run_id=run_id,
        role="assistant",
        content=content,
        provider="fake",
        model="model-a",
        provider_session_id=None,
        timestamp="2024-01-01T00:00:00+00:00",
    )


def test_append_message_and_read_history_roundtrip(transcript_store: TranscriptStore) -> None:
    transcript_store.append_message("session-1", _message("run-1", "hello"))

    history = transcript_store.read_history("session-1")
    assert len(history) == 1
    assert history[0]["content"] == "hello"
    assert history[0]["run_id"] == "run-1"


def test_requested_tool_ids_roundtrip_as_public_metadata(transcript_store: TranscriptStore) -> None:
    transcript_store.append_message(
        "session-tools",
        TranscriptMessage(
            run_id="run-tools",
            role="user",
            content="Compare these.",
            provider="fake",
            model="model-a",
            provider_session_id=None,
            timestamp="2024-01-01T00:00:00+00:00",
            requested_tool_ids=["market.compare", "market.evidence"],
        ),
    )

    record = transcript_store.read_history("session-tools")[0]
    assert record["requested_tool_ids"] == ["market.compare", "market.evidence"]
    assert to_public_message(record)["requestedToolIds"] == [
        "market.compare",
        "market.evidence",
    ]


def test_read_history_respects_limit(transcript_store: TranscriptStore) -> None:
    transcript_store.append_message("session-1", _message("run-1", "one"))
    transcript_store.append_message("session-1", _message("run-2", "two"))
    transcript_store.append_message("session-1", _message("run-3", "three"))

    history = transcript_store.read_history("session-1", limit=2)
    assert [item["content"] for item in history] == ["two", "three"]


def test_read_history_returns_empty_for_missing_session(transcript_store: TranscriptStore) -> None:
    assert transcript_store.read_history("missing") == []


def test_read_history_skips_malformed_jsonl_lines(transcript_store: TranscriptStore) -> None:
    path = transcript_store.transcript_path_for("session-1")
    path.write_text(
        "\n".join(
            [
                json.dumps(_message("run-1", "one").to_json()),
                "{not-json",
                json.dumps(_message("run-2", "two").to_json()),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    history = transcript_store.read_history("session-1")
    assert [item["content"] for item in history] == ["one", "two"]


def test_read_history_ignores_truncated_final_jsonl_record(transcript_store: TranscriptStore) -> None:
    path = transcript_store.transcript_path_for("session-1")
    path.write_text(
        json.dumps(_message("run-1", "durable").to_json()) + '\n{"run_id":"partial',
        encoding="utf-8",
    )

    history = transcript_store.read_history("session-1")
    assert [(item["run_id"], item["content"]) for item in history] == [("run-1", "durable")]


def test_two_transcript_store_instances_append_without_loss_and_preserve_writer_order(tmp_dir) -> None:
    stores = [TranscriptStore(root_dir=tmp_dir), TranscriptStore(root_dir=tmp_dir)]

    def append_series(store: TranscriptStore, prefix: str) -> None:
        for index in range(20):
            store.append_message("shared", _message(f"{prefix}-{index}", f"{prefix} {index}"))

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(append_series, stores[0], "left"),
            executor.submit(append_series, stores[1], "right"),
        ]
        for future in futures:
            future.result()

    history = stores[0].read_history("shared")
    run_ids = [item["run_id"] for item in history]
    assert len(run_ids) == 40
    assert len(set(run_ids)) == 40
    assert [run_id for run_id in run_ids if run_id.startswith("left-")] == [f"left-{index}" for index in range(20)]
    assert [run_id for run_id in run_ids if run_id.startswith("right-")] == [
        f"right-{index}" for index in range(20)
    ]


def test_transcript_message_roundtrips_structured_parts(transcript_store: TranscriptStore) -> None:
    transcript_store.append_message(
        "session-1",
        TranscriptMessage(
            run_id="run-1",
            role="assistant",
            content="I will inspect the repo.",
            provider="fake",
            model="model-a",
            provider_session_id=None,
            timestamp="2024-01-01T00:00:00+00:00",
            state="final",
            tool_execution={"toolId": "files.read", "ok": True, "summary": "Read README.md."},
            parts=[
                {"kind": "text", "text": "I will inspect the repo."},
                {"kind": "tool_call", "toolCall": {"toolId": "files.read", "arguments": {"path": "README.md"}}},
                {"kind": "tool_result", "toolExecution": {"toolId": "files.read", "ok": True, "summary": "Read README.md."}},
            ],
        ),
    )

    history = transcript_store.read_history("session-1")
    assert history[0]["parts"][1]["toolCall"]["toolId"] == "files.read"
