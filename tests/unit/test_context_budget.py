"""The provider-input budget must be able to see everything it is bounding.

The estimator covers message bodies, images, instructions and tool schemas; the
allocator then caps accumulated input at 60% of the selected model window.
"""

from __future__ import annotations

import json
import pytest

from copenet.core.harness.context_window import (
    estimate_input_tokens,
    estimate_request_tokens,
    group_by_user_turn,
    trim_messages_to_request_budget,
    trim_messages_to_token_budget,
)
from copenet.core.orchestrator.context_budget import (
    CONTEXT_INPUT_TARGET_TOKENS,
    discover_model_context_tokens,
    resolve_context_budget,
)
from copenet.providers import ProviderModel


def _text_turn(text: str) -> dict:
    return {"role": "user", "content": [{"type": "input_text", "text": text}]}


def _image_part(payload_chars: int) -> dict:
    return {
        "type": "input_image",
        "detail": "auto",
        "image_url": "data:image/png;base64," + ("A" * payload_chars),
    }


# -- measurement ----------------------------------------------------------------


def test_image_parts_are_not_invisible_to_the_estimator() -> None:
    with_image = [{"role": "user", "content": [{"type": "input_text", "text": "look"}, _image_part(400_000)]}]

    assert estimate_input_tokens(with_image) > 1_000


def test_image_heavy_conversation_is_actually_trimmed_at_the_product_target() -> None:
    """The exact regression: image payload used to estimate as 7 tokens and trim nothing.

    Two images legitimately fit in the product budget, so this uses a long vision thread
    — the realistic way a session accumulates enough image payload to overflow.
    """
    messages: list[dict] = []
    for index in range(20):
        messages.append(
            {"role": "user", "content": [{"type": "input_text", "text": f"shot {index}"}, _image_part(1_500_000)]}
        )
        messages.append(
            {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "ok"}]}
        )
    messages.append(_text_turn("now?"))

    assert estimate_input_tokens(messages) > CONTEXT_INPUT_TARGET_TOKENS

    trimmed = trim_messages_to_token_budget(messages, max_context_tokens=CONTEXT_INPUT_TARGET_TOKENS)

    assert len(trimmed) < len(messages)
    assert estimate_input_tokens(trimmed) <= CONTEXT_INPUT_TARGET_TOKENS
    assert trimmed[-1] == messages[-1], "the live turn is always retained"


def test_image_cost_estimate_stays_in_a_defensible_range() -> None:
    """Deliberately conservative, but not absurd — this pins the divisor's effect.

    A ~1.1 MB image really costs a frontier model on the order of 1-2K tokens. The
    estimator charges more than that on purpose (overflow is expensive, over-trimming
    is merely lossy), but it must not be so large that a single image evicts a
    conversation.
    """
    one_image = [{"role": "user", "content": [_image_part(1_500_000)]}]

    estimate = estimate_input_tokens(one_image)

    assert 2_000 < estimate < 20_000


def test_reasoning_items_are_charged_for_their_encrypted_payload() -> None:
    reasoning = {"type": "reasoning", "id": "rs_1", "encrypted_content": "Z" * 200_000, "summary": []}

    assert estimate_input_tokens([reasoning]) > 1_000


def test_unknown_item_types_cannot_cost_zero() -> None:
    """A shape we do not model yet must still consume budget, not vanish."""
    future_item = {"type": "compaction", "payload": {"blob": "q" * 40_000}}

    assert estimate_input_tokens([future_item]) > 1_000


def test_text_estimate_is_still_roughly_char_quarter() -> None:
    assert estimate_input_tokens([_text_turn("a" * 400)]) == 100


# -- trimming invariants ---------------------------------------------------------


def test_tool_call_and_result_are_never_split() -> None:
    messages = [
        _text_turn("A" * 4000),
        {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "B" * 4000}]},
        _text_turn("read it"),
        {"type": "function_call", "call_id": "c1", "name": "files_read", "arguments": '{"path":"x"}'},
        {"type": "function_call_output", "call_id": "c1", "output": "C" * 80},
        {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "done"}]},
        _text_turn("current"),
    ]

    trimmed = trim_messages_to_token_budget(messages, max_context_tokens=100)

    call_ids = [item["call_id"] for item in trimmed if item.get("type") in {"function_call", "function_call_output"}]
    assert call_ids in ([], ["c1", "c1"]), "a call must never appear without its result"


def test_oversized_current_user_item_is_rejected_before_provider_dispatch() -> None:
    messages = [_text_turn("old"), _text_turn("X" * 100_000)]

    with pytest.raises(ValueError, match="Current user turn"):
        trim_messages_to_token_budget(messages, max_context_tokens=10)


def test_live_tool_exchange_is_trimmed_as_a_complete_call_result_pair() -> None:
    messages = [
        _text_turn("current"),
        {"type": "function_call", "call_id": "old", "name": "read", "arguments": "{}"},
        {"type": "function_call_output", "call_id": "old", "output": "A" * 800},
        {"type": "function_call", "call_id": "new", "name": "read", "arguments": "{}"},
        {"type": "function_call_output", "call_id": "new", "output": "B" * 80},
    ]

    trimmed = trim_messages_to_token_budget(messages, max_context_tokens=40)

    assert [item.get("call_id") for item in trimmed[1:]] == ["new", "new"]


def test_grouping_attaches_tool_items_to_the_turn_that_caused_them() -> None:
    groups = group_by_user_turn(
        [
            _text_turn("first"),
            {"type": "function_call", "call_id": "c1", "name": "t", "arguments": "{}"},
            {"type": "function_call_output", "call_id": "c1", "output": "r"},
            _text_turn("second"),
        ]
    )

    assert len(groups) == 2
    assert len(groups[0]) == 3


def test_trimming_never_mutates_the_input_list() -> None:
    messages = [_text_turn("a" * 40_000), _text_turn("b")]
    snapshot = json.dumps(messages)

    trim_messages_to_token_budget(messages, max_context_tokens=10)

    assert json.dumps(messages) == snapshot


# -- budget resolution -----------------------------------------------------------


def test_provider_fallback_uses_sixty_percent_of_its_conservative_window() -> None:
    budget = resolve_context_budget(provider="openai-codex")

    assert budget.input_tokens == 120_000
    assert budget.reserved_output_tokens == 80_000


def test_280k_model_reaches_the_168k_absolute_product_ceiling() -> None:
    budget = resolve_context_budget(provider="openai-codex", model_context_tokens=280_000)

    assert budget.input_tokens == CONTEXT_INPUT_TARGET_TOKENS == 168_000
    assert budget.reserved_output_tokens == 112_000


def test_model_metadata_below_the_target_lowers_the_effective_budget() -> None:
    budget = resolve_context_budget(provider="lm-studio", model_context_tokens=16_000)

    assert budget.input_tokens == 9_600
    assert budget.input_tokens < CONTEXT_INPUT_TARGET_TOKENS
    assert budget.source == "model_metadata"


def test_unknown_providers_do_not_get_an_optimistic_window() -> None:
    budget = resolve_context_budget(provider="some-new-runtime")

    assert budget.input_tokens < CONTEXT_INPUT_TARGET_TOKENS
    assert budget.source == "provider_fallback"


def test_a_tiny_reported_window_is_never_overridden_by_a_dangerous_floor() -> None:
    budget = resolve_context_budget(provider="ollama", model_context_tokens=2_000)

    assert budget.input_tokens == 1_200
    assert budget.source == "model_metadata"


def test_complete_request_estimate_counts_instructions_and_tool_schemas() -> None:
    messages = [_text_turn("A" * 400)]
    tools = [{"type": "function", "name": "read", "description": "B" * 400, "parameters": {}}]

    message_tokens = estimate_input_tokens(messages)
    total_tokens = estimate_request_tokens(messages, instructions="C" * 400, tools=tools)

    assert total_tokens > message_tokens + 200


def test_request_budget_charges_fixed_overhead_before_retaining_history() -> None:
    messages = [_text_turn("old" * 400), _text_turn("current")]

    bounded = trim_messages_to_request_budget(
        messages,
        max_input_tokens=300,
        instructions="I" * 400,
        tools=[{"description": "T" * 400}],
    )

    assert bounded == [messages[-1]]
    assert estimate_request_tokens(bounded, instructions="I" * 400, tools=[{"description": "T" * 400}]) <= 300


@pytest.mark.asyncio
async def test_selected_model_declared_context_window_is_discovered() -> None:
    class Provider:
        async def list_models(self):
            return [ProviderModel(id="small", display_name="Small", provider="local", metadata={"maxContextLength": 32_000}),
                    ProviderModel(id="large", display_name="Large", provider="local", metadata={"maxContextLength": "280000"})]

    assert await discover_model_context_tokens(Provider(), "large") == 280_000
    assert await discover_model_context_tokens(Provider(), "missing") is None
