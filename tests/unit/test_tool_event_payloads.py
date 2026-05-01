from __future__ import annotations

from copenet.core.tools import ToolExecutionResult


def test_tool_execution_event_payload_includes_files_read_preview() -> None:
    payload = ToolExecutionResult(
        tool_id="files.read",
        ok=True,
        summary="Read file README.md.",
        output={"path": "README.md", "content": "# Title\nhello\n"},
        body={"path": "README.md", "content": "# Title\nhello\n"},
    ).to_event_payload()

    assert payload["preview"] == {"path": "README.md", "content": "# Title\nhello"}


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
            "preview": {"path": "docs/tests/TEST_FILE.md", "content": "alpha\nbeta"},
        },
        {
            "toolId": "files.read",
            "ok": True,
            "summary": "Read file docs/tests/TEST_FILE_2.md.",
            "error": None,
            "preview": {"path": "docs/tests/TEST_FILE_2.md", "content": "gamma\ndelta"},
        },
    ]

