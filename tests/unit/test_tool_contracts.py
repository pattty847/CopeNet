from copenet.core.tools import (
    ToolDescriptor,
    build_openai_tool_schemas,
    build_tool_prompt_section,
    extract_final_candidate,
    extract_tool_batch_invocation,
    extract_tool_invocation,
)


def test_extract_tool_invocation_from_valid_json() -> None:
    envelope = extract_tool_invocation('{"tool_id":"files.read","arguments":{"path":"README.md"}}')
    assert envelope is not None
    assert envelope.tool_id == "files.read"
    assert envelope.arguments == {"path": "README.md"}


def test_extract_tool_invocation_returns_none_for_prose() -> None:
    assert extract_tool_invocation("I should probably inspect the repo first.") is None


def test_extract_tool_invocation_from_fenced_json_block() -> None:
    envelope = extract_tool_invocation(
        """```json
{"toolId":"git.status","arguments":{}}
```"""
    )
    assert envelope is not None
    assert envelope.tool_id == "git.status"
    assert envelope.arguments == {}


def test_extract_tool_invocation_from_single_tool_calls_wrapper() -> None:
    envelope = extract_tool_invocation(
        '{"tool_calls":[{"tool_id":"files.read","arguments":{"path":"README.md"}}]}'
    )
    assert envelope is not None
    assert envelope.tool_id == "files.read"
    assert envelope.arguments == {"path": "README.md"}


def test_extract_tool_batch_invocation_from_valid_json() -> None:
    envelope = extract_tool_batch_invocation(
        '{"tool_calls":[{"tool_id":"files.list","arguments":{"path":"."}},{"tool_id":"files.read","arguments":{"path":"README.md"}}]}'
    )
    assert envelope is not None
    requests = envelope.to_requests()
    assert [request.tool_id for request in requests] == ["files.list", "files.read"]


def test_extract_tool_batch_invocation_returns_none_for_single_call() -> None:
    assert (
        extract_tool_batch_invocation('{"tool_calls":[{"tool_id":"files.list","arguments":{"path":"."}}]}')
        is None
    )


def test_extract_tool_batch_invocation_from_adjacent_tool_objects() -> None:
    envelope = extract_tool_batch_invocation(
        '{"tool_id":"files.read","arguments":{"path":"README.md"}} '
        '{"tool_id":"files.read","arguments":{"path":"TODO.md"}} '
        '{"tool_id":"files.read","arguments":{"path":"AGENTS.md"}}'
    )
    assert envelope is not None
    requests = envelope.to_requests()
    assert [request.tool_id for request in requests] == ["files.read", "files.read", "files.read"]
    assert [request.arguments["path"] for request in requests] == ["README.md", "TODO.md", "AGENTS.md"]


def test_build_tool_prompt_section_returns_empty_for_no_tools() -> None:
    assert build_tool_prompt_section([]) == ""


def test_extract_final_candidate_from_valid_json() -> None:
    envelope = extract_final_candidate(
        '{"state":"FINAL_CANDIDATE","answer":"Done.","evidence":["README.md"],"done_conditions_met":["grounded evidence"],"remaining_uncertainty":[]}'
    )
    assert envelope is not None
    assert envelope.answer == "Done."
    assert envelope.evidence == ["README.md"]


def test_extract_final_candidate_normalizes_missing_list_fields() -> None:
    envelope = extract_final_candidate('{"state":"FINAL_CANDIDATE","answer":"Done."}')
    assert envelope is not None
    assert envelope.evidence == []
    assert envelope.done_conditions_met == []
    assert envelope.remaining_uncertainty == []


def test_extract_final_candidate_rejects_empty_answer() -> None:
    assert extract_final_candidate('{"state":"FINAL_CANDIDATE","answer":"   "}') is None


def test_extract_final_candidate_accepts_type_and_content_aliases() -> None:
    envelope = extract_final_candidate(
        '{"type":"FINAL_CANDIDATE","content":"Done from alias.","evidence":["README.md"]}'
    )
    assert envelope is not None
    assert envelope.answer == "Done from alias."
    assert envelope.evidence == ["README.md"]


def test_build_tool_prompt_section_lists_all_tool_ids() -> None:
    tools = [
        ToolDescriptor(id="files.read", name="Read File", description="Read one file.", category="repo-read"),
        ToolDescriptor(id="git.status", name="Git Status", description="Read git status.", category="repo-read"),
    ]

    section = build_tool_prompt_section(tools)
    assert "files.read" in section
    assert "git.status" in section
    assert "tool_calls" in section
    assert "FINAL_CANDIDATE" in section


def test_build_openai_tool_schemas_uses_tool_ids_as_function_names() -> None:
    tools = [
        ToolDescriptor(
            id="files.read",
            name="Read File",
            description="Read one file.",
            category="repo-read",
            input_schema={
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        )
    ]

    schemas = build_openai_tool_schemas(tools)

    assert schemas == [
        {
            "type": "function",
            "function": {
                "name": "files.read",
                "description": "Read one file.",
                "parameters": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            },
        }
    ]
