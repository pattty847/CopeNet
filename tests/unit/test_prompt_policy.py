from __future__ import annotations

from copenet.prompts import (
    PromptPurpose,
    compose_prompt,
    prompt_context_policy,
    prompt_context_policy_for_chat,
)


def test_default_profile_is_minimal() -> None:
    assert compose_prompt("default", "none") == "# Default\n\nBe a helpful AI."


def test_general_chat_excludes_agent_notes_and_ranked_memory() -> None:
    policy = prompt_context_policy_for_chat("default")

    assert policy.purpose == PromptPurpose.GENERAL_CHAT
    assert policy.include_persona_context is True
    assert policy.include_persona_agent_instructions is False
    assert policy.include_relevant_memory is False


def test_code_profiles_include_agent_notes_but_not_ranked_memory() -> None:
    for profile_id in ("builder", "code-review", "debug", "refactor"):
        policy = prompt_context_policy_for_chat(profile_id)
        assert policy.purpose == PromptPurpose.CODE
        assert policy.include_persona_agent_instructions is True
        assert policy.include_relevant_memory is False


def test_utility_requests_receive_no_ambient_context() -> None:
    policy = prompt_context_policy(PromptPurpose.UTILITY)

    assert policy.include_persona_context is False
    assert policy.include_persona_agent_instructions is False
    assert policy.include_relevant_memory is False
