from copenet.core.tools import (
    ToolDescriptor,
    ToolRegistry,
    build_openai_tool_schemas,
    describe_available_tools,
)


def test_describe_available_tools_returns_compact_manifest_details() -> None:
    tools = [
        ToolDescriptor(id="files.read", name="Read File", description="Read one file.", category="repo-read"),
        ToolDescriptor(id="files.edit", name="Edit File", description="Edit one file.", category="repo-write"),
    ]

    described = describe_available_tools(tools)

    assert described[0]["id"] == "files.read"
    assert described[0]["approvalMode"] == "auto_allowed"
    assert described[1]["id"] == "files.edit"
    assert described[1]["approvalMode"] == "policy_gated"


def test_describe_available_tools_can_filter_by_tool_id() -> None:
    tools = [
        ToolDescriptor(id="files.read", name="Read File", description="Read one file.", category="repo-read"),
        ToolDescriptor(id="files.edit", name="Edit File", description="Edit one file.", category="repo-write"),
    ]

    described = describe_available_tools(tools, tool_ids=["files.edit"])

    assert [tool["id"] for tool in described] == ["files.edit"]


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


def test_tool_registry_does_not_expose_removed_experimental_tools() -> None:
    tool_ids = {tool.id for tool in ToolRegistry().list_tools()}

    assert "patch.plan" not in tool_ids
    assert "tools.describe" not in tool_ids
