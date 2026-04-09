import json

from copenet.core.sessions import TranscriptMessage, TranscriptStore


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
