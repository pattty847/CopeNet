from __future__ import annotations

import json

import pytest

from copenet.core.harness.decision import (
    HarnessDecisionValidationError,
    make_unavailable_decision_record,
    parse_harness_decision_record,
)


def test_parse_harness_decision_record_preserves_trace_only_prose_fields() -> None:
    raw = json.dumps(
        {
            "user_goal": "Fix the reconnect bug without guessing.",
            "request_kind": "code",
            "route": "call_tool",
            "next_action": "SEARCH_FILES",
            "risk": "medium",
            "evidence_requirements": ["direct_file_grounding", "verify_before_done"],
            "tool_decision": {
                "needed": True,
                "candidate_tool_ids": ["files.search", "files.read"],
                "selected_tool_id": "files.search",
                "trace_note": "Need to locate the reconnect implementation first.",
            },
            "missing": ["current reconnect implementation"],
            "assumptions": ["active workspace is the target repo"],
            "trace_note": "Start with discovery, then read exact files.",
        }
    )

    record = parse_harness_decision_record(
        raw,
        turn_id="turn-1",
        decision_id="decision-1",
        available_tool_ids={"files.search", "files.read"},
    )

    assert record.to_public_dict() == {
        "schema_version": "harness_decision_record.v1",
        "decision_id": "decision-1",
        "turn_id": "turn-1",
        "control_mode": "trace_only",
        "status": "parsed",
        "decision": {
            "user_goal": "Fix the reconnect bug without guessing.",
            "request_kind": "code",
            "route": "call_tool",
            "next_action": "SEARCH_FILES",
            "risk": "medium",
            "evidence_requirements": ["direct_file_grounding", "verify_before_done"],
            "tool_decision": {
                "needed": True,
                "candidate_tool_ids": ["files.search", "files.read"],
                "selected_tool_id": "files.search",
                "trace_note": "Need to locate the reconnect implementation first.",
            },
            "missing": ["current reconnect implementation"],
            "assumptions": ["active workspace is the target repo"],
            "trace_note": "Start with discovery, then read exact files.",
        },
    }


def test_parse_harness_decision_record_rejects_unknown_enums_and_invented_tools() -> None:
    raw = json.dumps(
        {
            "user_goal": "Read the repo.",
            "request_kind": "code",
            "route": "keyword_magic",
            "next_action": "SEARCH_FILES",
            "risk": "low",
            "evidence_requirements": ["direct_file_grounding"],
            "tool_decision": {
                "needed": True,
                "candidate_tool_ids": ["read_file"],
                "selected_tool_id": "read_file",
                "trace_note": "Invented tool id should not pass.",
            },
            "trace_note": "Nope.",
        }
    )

    with pytest.raises(HarnessDecisionValidationError):
        parse_harness_decision_record(
            raw,
            turn_id="turn-1",
            decision_id="decision-1",
            available_tool_ids={"files.read"},
        )


def test_unavailable_harness_decision_record_is_first_class() -> None:
    record = make_unavailable_decision_record(
        turn_id="turn-1",
        decision_id="decision-1",
        error_summary="Provider has no decision hook.",
    )

    assert record.to_public_dict() == {
        "schema_version": "harness_decision_record.v1",
        "decision_id": "decision-1",
        "turn_id": "turn-1",
        "control_mode": "trace_only",
        "status": "unavailable",
        "decision": None,
        "error_summary": "Provider has no decision hook.",
    }
