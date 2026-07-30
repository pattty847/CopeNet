from copenet.core.tools import (
    ToolDescriptor,
    ToolRegistry,
    ToolExecutionResult,
    build_tool_effect_payload,
    build_openai_tool_schemas,
    describe_available_tools,
)


def test_describe_available_tools_returns_compact_manifest_details() -> None:
    tools = ToolRegistry().list_tools()

    described = describe_available_tools(tools, tool_ids=["files.read", "files.edit"])
    by_id = {tool["id"]: tool for tool in described}

    assert by_id["files.read"]["approvalMode"] == "auto_allowed"
    assert by_id["files.read"]["evidenceRole"] == "grounding"
    assert by_id["files.read"]["sideEffect"] == "read"
    assert by_id["files.read"]["requiresConfirmation"] is False
    assert by_id["files.edit"]["approvalMode"] == "policy_gated"
    assert by_id["files.edit"]["evidenceRole"] == "mutation"
    assert by_id["files.edit"]["sideEffect"] == "write"


def test_describe_available_tools_can_filter_by_tool_id() -> None:
    tools = [
        ToolDescriptor(id="files.read", name="Read File", description="Read one file.", category="repo-read"),
        ToolDescriptor(id="files.edit", name="Edit File", description="Edit one file.", category="repo-write"),
    ]

    described = describe_available_tools(tools, tool_ids=["files.edit"])

    assert [tool["id"] for tool in described] == ["files.edit"]


def test_files_rg_description_distinguishes_content_search_from_path_lookup() -> None:
    descriptor = next(tool for tool in ToolRegistry().list_tools() if tool.id == "files.rg")

    assert "contents only" in descriptor.description
    assert "filenames or directory paths" in descriptor.description
    assert "shell.exec with find" in descriptor.description
    assert "file contents only" in descriptor.input_schema["properties"]["pattern"]["description"]


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


def test_build_tool_effect_payload_links_turn_decision_and_evidence_role() -> None:
    descriptor = ToolDescriptor(
        id="files.read",
        name="Read File",
        description="Read one file.",
        category="repo-read",
        evidence_role="grounding",
        side_effect="read",
    )
    result = ToolExecutionResult(
        tool_id="files.read",
        call_id="files.read-abc",
        ok=True,
        summary="Read file README.md.",
        output={"path": "README.md", "content": "# Title\nhello\n"},
        body={"path": "README.md", "content": "# Title\nhello\n"},
    )

    effect = build_tool_effect_payload(
        result=result,
        arguments={"path": "README.md"},
        descriptor=descriptor,
        turn_id="turn-1",
        decision_id="decision-1",
    )

    assert effect == {
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


def test_tool_registry_does_not_expose_removed_experimental_tools() -> None:
    tool_ids = {tool.id for tool in ToolRegistry().list_tools()}

    assert {"patch.plan", "tools.describe", "context.prepare"}.isdisjoint(tool_ids)
    assert "market.evidence" in tool_ids
