from __future__ import annotations

from copenet.core.tools import ToolExecutionResult


def test_tool_execution_event_payload_includes_files_read_preview() -> None:
    payload = ToolExecutionResult(
        tool_id="files.read",
        call_id="files.read-abc",
        ok=True,
        summary="Read file README.md.",
        output={"path": "README.md", "content": "# Title\nhello\n"},
        body={"path": "README.md", "content": "# Title\nhello\n"},
    ).to_event_payload(
        turn_id="turn-1",
        decision_id="decision-1",
        arguments={"path": "README.md"},
        evidence_role="grounding",
    )

    assert payload["preview"] == {
        "path": "README.md",
        "content": "# Title\nhello",
        "startLine": 1,
        "totalLines": 2,
    }
    assert payload["turnId"] == "turn-1"
    assert payload["decisionId"] == "decision-1"
    assert payload["effect"] == {
        "schema_version": "tool_effect.v1",
        "effect_id": "effect-files.read-abc",
        "decision_id": "decision-1",
        "turn_id": "turn-1",
        "tool_id": "files.read",
        "kind": "file_read",
        "target": "README.md",
        "preview": {
            "path": "README.md",
            "content": "# Title\nhello",
            "startLine": 1,
            "totalLines": 2,
        },
        "artifact_id": None,
        "evidence_role": "grounding",
    }


def test_files_read_preview_preserves_ranged_read_start_line() -> None:
    payload = ToolExecutionResult(
        tool_id="files.read",
        ok=True,
        summary="Read file README.md lines 41-42.",
        output={"path": "README.md", "content": "alpha\nbeta", "startLine": 41, "endLine": 42, "totalLines": 100},
        body={"path": "README.md", "content": "alpha\nbeta", "startLine": 41, "endLine": 42, "totalLines": 100},
    ).to_event_payload()

    assert payload["preview"] == {
        "path": "README.md",
        "content": "alpha\nbeta",
        "startLine": 41,
        "totalLines": 2,
    }


def test_tool_execution_event_payload_includes_grouped_batch_members() -> None:
    payload = ToolExecutionResult(
        tool_id="tool.batch",
        ok=True,
        summary="Read file a.md.; Read file b.md.",
        output={
            "results": [
                {
                    "toolId": "files.read",
                    "ok": True,
                    "summary": "Read file docs/tests/TEST_FILE.md.",
                    "output": {"path": "docs/tests/TEST_FILE.md", "content": "alpha\nbeta\n"},
                    "error": None,
                },
                {
                    "toolId": "files.read",
                    "ok": True,
                    "summary": "Read file docs/tests/TEST_FILE_2.md.",
                    "output": {"path": "docs/tests/TEST_FILE_2.md", "content": "gamma\ndelta\n"},
                    "error": None,
                },
            ]
        },
        body={
            "results": [
                {
                    "toolId": "files.read",
                    "ok": True,
                    "summary": "Read file docs/tests/TEST_FILE.md.",
                    "output": {"path": "docs/tests/TEST_FILE.md", "content": "alpha\nbeta\n"},
                    "error": None,
                },
                {
                    "toolId": "files.read",
                    "ok": True,
                    "summary": "Read file docs/tests/TEST_FILE_2.md.",
                    "output": {"path": "docs/tests/TEST_FILE_2.md", "content": "gamma\ndelta\n"},
                    "error": None,
                },
            ]
        },
    ).to_event_payload()

    assert payload["members"] == [
        {
            "toolId": "files.read",
            "ok": True,
            "summary": "Read file docs/tests/TEST_FILE.md.",
            "error": None,
            "preview": {
                "path": "docs/tests/TEST_FILE.md",
                "content": "alpha\nbeta",
                "startLine": 1,
                "totalLines": 2,
            },
        },
        {
            "toolId": "files.read",
            "ok": True,
            "summary": "Read file docs/tests/TEST_FILE_2.md.",
            "error": None,
            "preview": {
                "path": "docs/tests/TEST_FILE_2.md",
                "content": "gamma\ndelta",
                "startLine": 1,
                "totalLines": 2,
            },
        },
    ]
