from copenet.core.tools import ToolDescriptor, build_tool_prompt_section, extract_tool_invocation


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


def test_build_tool_prompt_section_returns_empty_for_no_tools() -> None:
    assert build_tool_prompt_section([]) == ""


def test_build_tool_prompt_section_lists_all_tool_ids() -> None:
    tools = [
        ToolDescriptor(id="files.read", name="Read File", description="Read one file.", category="repo-read"),
        ToolDescriptor(id="git.status", name="Git Status", description="Read git status.", category="repo-read"),
    ]

    section = build_tool_prompt_section(tools)
    assert "files.read" in section
    assert "git.status" in section
