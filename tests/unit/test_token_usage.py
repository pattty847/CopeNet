"""Provider-reported token usage is summed per run and never invented."""

from __future__ import annotations

from copenet.core.orchestrator.token_usage import summarize_token_usage
from copenet.core.runtime.runs import RunRecord
from copenet.providers import TOKEN_USAGE_META_KEY, token_usage_event


def test_summary_sums_billed_input_and_keeps_the_peak_context() -> None:
    steps = [
        {"inputTokens": 23_086, "outputTokens": 400, "cachedInputTokens": None, "reasoningTokens": 200, "call": 1},
        {"inputTokens": 50_466, "outputTokens": 300, "cachedInputTokens": 20_000, "reasoningTokens": None, "call": 2},
        {"inputTokens": 52_079, "outputTokens": 1_830, "cachedInputTokens": 45_000, "reasoningTokens": 512, "call": 3},
    ]

    summary = summarize_token_usage(steps)

    assert summary["modelCalls"] == 3
    assert summary["inputTokens"] == 125_631
    assert summary["peakInputTokens"] == 52_079
    assert summary["outputTokens"] == 2_530
    assert summary["cachedInputTokens"] == 65_000
    assert summary["reasoningTokens"] == 712
    assert summary["source"] == "provider"


def test_no_reported_usage_means_no_summary_not_zero() -> None:
    assert summarize_token_usage([]) is None
    assert token_usage_event(input_tokens=None, output_tokens=None) is None


def test_usage_event_rejects_non_counts() -> None:
    event = token_usage_event(input_tokens="12", output_tokens=7.0, cached_input_tokens=True)

    assert event.metadata[TOKEN_USAGE_META_KEY] == {
        "inputTokens": None, "outputTokens": 7, "cachedInputTokens": None, "reasoningTokens": None,
    }


def test_run_record_round_trips_token_usage_and_exposes_it_publicly() -> None:
    record = RunRecord(
        run_id="r", session_key="s", provider="openai-codex", model="gpt-5.5", status="ok",
        user_message="m", tool_execution_mode="responses", will_attempt_tool_loop=True,
        token_usage=summarize_token_usage([{"inputTokens": 10, "outputTokens": 2, "call": 1}]),
    )

    restored = RunRecord.from_json(record.to_json())

    assert restored.token_usage == record.token_usage
    assert restored.to_public_dict()["tokenUsage"]["peakInputTokens"] == 10
    assert RunRecord.from_json({**record.to_json(), "token_usage": None}).to_public_dict()["tokenUsage"] is None
