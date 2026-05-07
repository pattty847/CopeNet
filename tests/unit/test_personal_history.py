import pytest

from copenet.core.orchestrator.personal_history import (
    extract_personal_questions,
    extract_resume_decisions,
    normalize_personal_focus,
    normalize_starter_intent,
    starter_intent_tags,
)


def test_normalize_starter_intent_rejects_unknown_values() -> None:
    assert normalize_starter_intent("plan_my_next_steps") == "plan_my_next_steps"
    assert normalize_starter_intent("  reflect_and_organize  ") == "reflect_and_organize"
    assert normalize_starter_intent("unknown") is None


def test_starter_intent_tags_match_personal_intent() -> None:
    assert starter_intent_tags("think_through_something") == ["thinking", "clarity"]
    assert starter_intent_tags("plan_my_next_steps") == ["planning", "execution"]
    assert starter_intent_tags("reflect_and_organize") == ["reflection", "organization"]


def test_extract_personal_questions_collects_user_and_assistant_questions() -> None:
    questions = extract_personal_questions(
        "How should I handle this project? What am I missing?",
        "Open questions:\n- Who owns the deadline?\n- What can slip?",
    )

    assert "How should I handle this project?" in questions
    assert "What am I missing?" in questions
    assert "Who owns the deadline?" in questions
    assert "What can slip?" in questions


def test_extract_resume_decisions_pulls_structured_decision_lines() -> None:
    decisions = extract_resume_decisions(
        "Key decisions:\n- Start with the customer email.\n- Keep the launch scoped to one page.\n\nOpen questions:\n- Do we need analytics?"
    )

    assert decisions == [
        "Start with the customer email.",
        "Keep the launch scoped to one page.",
    ]


def test_normalize_personal_focus_compacts_whitespace() -> None:
    focus = normalize_personal_focus("  Help me   think through   the next move for this launch.  ")
    assert focus == "Help me think through the next move for this launch."
