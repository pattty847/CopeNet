from copenet.core.orchestrator.tool_requests import (
    append_system_overlay,
    normalize_requested_tool_ids,
    requested_tool_overlay,
)


def test_normalize_requested_tool_ids_keeps_registered_unique_order():
    assert normalize_requested_tool_ids(
        ("market.compare", " files.rg ", "market.compare", "unknown.tool", ""),
        registered_tool_ids=("files.rg", "market.compare"),
    ) == ("market.compare", "files.rg")


def test_requested_tool_overlay_is_turn_scoped_and_explicit():
    overlay = requested_tool_overlay(("market.compare", "market.evidence"))

    assert overlay is not None
    assert "<operator_requested_tools>" in overlay
    assert "`market.compare`" in overlay
    assert "`market.evidence`" in overlay
    assert "Do not invent missing arguments" in overlay


def test_append_system_overlay_preserves_base_prompt():
    assert append_system_overlay("Base instructions.", "Turn overlay.") == (
        "Base instructions.\n\nTurn overlay."
    )
