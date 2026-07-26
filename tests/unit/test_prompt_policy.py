from __future__ import annotations

from copenet.prompts import (
    PromptPurpose,
    compose_prompt,
    prompt_context_policy,
    prompt_context_policy_for_chat,
)
from copenet.prompts.loader import PERSONA_PLACEHOLDER


def test_default_profile_composes_the_base_contract_and_a_persona_slot() -> None:
    """The default composition is the base agent contract, not a bare profile line.

    Previously this asserted the whole prompt was "# Default\n\nBe a helpful AI." —
    accurate at the time, and the reason the harness shipped with no behavioral
    contract at all. The profile line is still there; it is now the smallest layer.
    """
    composed = compose_prompt("default", "none") or ""

    assert composed.startswith("# CopeNet Agent")
    assert PERSONA_PLACEHOLDER in composed
    assert "Be a helpful AI." in composed


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
