from __future__ import annotations

import ast
from pathlib import Path


def test_every_market_fetch_ohlcv_call_explicitly_requests_split_adjustment() -> None:
    market_root = Path(__file__).resolve().parents[2] / "src" / "copenet" / "core" / "market"
    violations: list[str] = []

    for path in sorted(market_root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            called_name = (
                node.func.id
                if isinstance(node.func, ast.Name)
                else node.func.attr
                if isinstance(node.func, ast.Attribute)
                else None
            )
            if called_name != "fetch_ohlcv":
                continue
            adjustment = next(
                (keyword.value for keyword in node.keywords if keyword.arg == "auto_adjust"),
                None,
            )
            if not (
                isinstance(adjustment, ast.Constant)
                and adjustment.value is True
            ):
                relative = path.relative_to(market_root.parent.parent.parent.parent)
                violations.append(f"{relative}:{node.lineno}")

    assert not violations, (
        "Every Market fetch_ohlcv caller must explicitly pass auto_adjust=True; "
        f"violations: {violations}"
    )
