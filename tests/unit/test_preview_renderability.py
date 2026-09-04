"""Every preview shape the backend emits must be one the inspector can render.

The market tools shipped five preview types — `market_compare`, `market_ticker`,
`market_dashboard`, `market_evidence`, `market_financials` — that the frontend
never had a renderer for. Every market tool call therefore rendered blank in the
inspector: the operator saw the call happen and no output at all. Worse, the
projections were lossy, so even with a renderer `market.compare` would have shown
only the ticker symbols and never the comparison rows.

This test is the guard: add a projection, ship its renderer, or don't add it.
"""

from __future__ import annotations

from pathlib import Path
import re

from copenet.core.tools.projection import _generic_preview, _preview_payload


CONTRACTS = Path(__file__).resolve().parents[2] / "src" / "copenet" / "core" / "tools" / "projection.py"
FRONTEND_TYPES = (
    Path(__file__).resolve().parents[2]
    / "src" / "copenet" / "host" / "frontend" / "src" / "types" / "backend.ts"
)


def _emitted_preview_types() -> set[str]:
    """Preview `type` literals produced by projection.py."""
    source = CONTRACTS.read_text(encoding="utf-8")
    # Only the preview builders use this exact key shape; JSON-schema "type": "object"
    # and "function" are tool schemas, not previews.
    found = set(re.findall(r'"type": "([a-z_]+)"', source))
    return found - {"object", "function"}


def _rendered_preview_types() -> set[str]:
    """Preview `type` literals the frontend's ToolResultPreview union declares."""
    source = FRONTEND_TYPES.read_text(encoding="utf-8")
    union = re.search(r"export type ToolResultPreview =(.*?);", source, re.S)
    assert union, "ToolResultPreview union not found — did the type move?"
    members = re.findall(r"\|?\s*(\w+Preview)", union.group(1))
    assert members, "no union members parsed"
    rendered: set[str] = set()
    for member in members:
        block = re.search(rf"export interface {member} \{{(.*?)\n\}}", source, re.S)
        assert block, f"{member} interface not found"
        literal = re.search(r"type: '([a-z_]+)'", block.group(1))
        assert literal, f"{member} declares no type literal"
        rendered.add(literal.group(1))
    return rendered


def test_every_emitted_preview_type_has_a_frontend_renderer() -> None:
    orphaned = _emitted_preview_types() - _rendered_preview_types()
    assert not orphaned, (
        f"projection.py emits preview types the inspector cannot render: {sorted(orphaned)}. "
        "Add the renderer to ToolResultPreview, or drop the projection and let "
        "_generic_preview return a raw body."
    )


def test_a_market_result_falls_through_to_a_renderable_raw_body() -> None:
    body = {
        "rows": [
            {"symbol": "AAPL", "last": 200.0, "changePct": 1.2},
            {"symbol": "MSFT", "last": 400.0, "changePct": -0.4},
        ],
        "asOf": "2026-08-02",
    }
    preview = _preview_payload("market.compare", body)

    assert preview is not None
    assert preview["type"] == "raw"
    # The rows are the point of the call; the old projection kept only the symbols.
    assert "AAPL" in preview["text"]
    assert "changePct" in preview["text"]


def test_an_oversized_body_is_clipped_honestly_rather_than_dropped() -> None:
    preview = _generic_preview({"rows": ["x" * 200 for _ in range(200)]})

    assert preview["type"] == "raw"
    assert preview["truncated"] is True
    assert preview["fullChars"] > len(preview["text"])
