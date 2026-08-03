"""Audit what the inspector actually shows for every registered tool.

The market tools rendered blank for months because their preview types had no
frontend renderer, and `market.compare` additionally discarded the comparison
rows that were the point of the call. Neither failure raises anything — the
output just silently isn't there — so the only way to catch the class is to run
each tool and measure what survives into the preview.

Two signals per tool:

- **renderable** — does the preview `type` appear in the frontend's
  `ToolResultPreview` union? A type with no renderer displays as nothing.
- **retention** — preview characters as a fraction of the real body. A tool can
  be perfectly renderable and still useless: `market.ticker` used to project
  symbol/last/change out of a body with dozens of fields, which reads as working.

Writes go to a temp workspace, so files.write / files.edit are safe to exercise.
Network tools are real calls — pass --offline to skip them.

    uv run python scripts/tool_output_audit.py
    uv run python scripts/tool_output_audit.py --offline --json
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import re
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from copenet.core.memory import MemoryService  # noqa: E402
from copenet.core.memory.store import MemoryStore  # noqa: E402
from copenet.core.persona import PersonaHomeService  # noqa: E402
from copenet.core.sessions import SessionStore, TranscriptStore  # noqa: E402
from copenet.core.user_notes.service import UserNotesService  # noqa: E402
from copenet.core.user_notes.store import UserNotesStore  # noqa: E402
from copenet.core.tools import (  # noqa: E402
    ToolExecutionContext,
    ToolExecutionRequest,
    ToolPolicy,
    ToolRegistry,
    policy_for_task_mode,
)
from copenet.core.tools.contracts import _preview_payload  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
FRONTEND_TYPES = REPO / "src" / "copenet" / "host" / "frontend" / "src" / "types" / "backend.ts"

# Tools that reach the network. Real calls, real latency, real rate limits.
NETWORK_TOOLS = {
    "market.backtest",
    "market.compare",
    "market.dashboard",
    "market.evidence",
    "market.financials",
    "market.ticker",
    "web.fetch",
    "web.search",
}

# Realistic arguments — the point is to see what a genuine call renders as, so
# these mirror what a model actually sends rather than minimal valid stubs.
FIXTURES: dict[str, dict] = {
    "files.read": {"path": "README.md", "limit": 40},
    "files.rg": {"pattern": "def ", "path": "src/copenet/core/tools", "limit": 20},
    "files.write": {"path": "audit_probe.txt", "content": "audit probe\n"},
    "files.edit": {"path": "audit_probe.txt", "old_text": "audit probe", "new_text": "audit probe edited"},
    "shell.exec": {"command": "ls"},
    "plan.write": {"items": [{"content": "Audit tool previews", "status": "in_progress"}]},
    "memory.read": {"limit": 5},
    "memory.write": {"category": "project_convention", "summary": "Audit probe entry", "detail": "Written by tool_output_audit."},
    "user.remember": {"target_section": "preferences", "summary": "Audit probe", "body": "Written by tool_output_audit."},
    "persona.author": {"personaId": "audit-probe", "displayName": "Audit Probe", "soul": "probe"},
    "market.dashboard": {},
    "market.ticker": {"symbol": "AAPL"},
    "market.compare": {"symbols": ["AAPL", "MSFT"]},
    "market.evidence": {"symbol": "AAPL", "limit": 5},
    "market.financials": {"symbol": "AAPL", "metric": "revenue", "frequency": "quarterly"},
    "market.backtest": {
        "mode": "portfolio",
        "symbols": ["AAPL", "MSFT"],
        "weights": [0.5, 0.5],
        "startDate": "2024-01-01",
        "endDate": "2024-12-31",
    },
    "web.search": {"query": "CopeNet agent harness", "limit": 3},
    "web.fetch": {"url": "https://example.com"},
}


def rendered_preview_types() -> set[str]:
    """Preview `type` literals the frontend can actually display."""
    source = FRONTEND_TYPES.read_text(encoding="utf-8")
    union = re.search(r"export type ToolResultPreview =(.*?);", source, re.S)
    if not union:
        return set()
    rendered: set[str] = set()
    for member in re.findall(r"\|?\s*(\w+Preview)", union.group(1)):
        block = re.search(rf"export interface {member} \{{(.*?)\n\}}", source, re.S)
        if not block:
            continue
        literal = re.search(r"type: '([a-z_]+)'", block.group(1))
        if literal:
            rendered.add(literal.group(1))
    return rendered


# Mirrors normalizeToolResultPreview in src/lib/wsNormalizers.ts. The client does
# NOT only read `type` — it sniffs shapes, so an untyped `{path, content}` still
# resolves to file_read and an untyped `{matches: [...]}` to repo_search. Auditing
# the backend payload alone reports those as broken when they render fine.
CLIENT_MAX_CHARS = 500  # DEFAULT_PREVIEW_LIMITS.maxChars


def resolve_client_preview(preview: dict | None) -> tuple[str | None, str]:
    """Return (resolved type, how it resolved), as the browser would see it."""
    if not preview:
        return None, "nothing"
    declared = str(preview.get("type") or "")
    if declared in {"file_read", "repo_search", "diff", "plan", "web_search", "web_doc"}:
        return declared, "declared"
    if isinstance(preview.get("path"), str) and isinstance(preview.get("content"), str):
        return "file_read", "sniffed"
    if isinstance(preview.get("matches"), list):
        return "repo_search", "sniffed"
    if isinstance(preview.get("preview"), str):
        return "raw", "declared" if declared == "raw" else "sniffed"
    if declared == "raw":
        return "raw", "declared"
    # Final fallback: JSON.stringify(payload).slice(0, 500). Renders, but as an
    # envelope dump clipped mid-token rather than the tool's actual output.
    return "raw", "json_dump"


def redact(text: str) -> str:
    """Strip the operator's home path out of samples.

    files.rg returns absolute paths, so an unredacted report carries the local
    username — which this repo's contributor guide forbids committing.
    """
    return text.replace(str(Path.home()), "~").replace(str(REPO), "<repo>")


def preview_text(preview: dict | None) -> str:
    """What the operator would read, for size comparison."""
    if not preview:
        return ""
    kind = preview.get("type")
    if kind == "raw":
        return str(preview.get("text") or "")
    if kind == "file_read":
        return "\n".join(preview.get("lines") or [])
    if kind == "diff":
        return str(preview.get("diff") or "")
    if kind == "repo_search":
        return "\n".join(
            f"{row.get('path')}:{row.get('line')} {row.get('snippet')}"
            for row in preview.get("matches") or []
        )
    return json.dumps(preview, ensure_ascii=False)


def build_context(workspace: Path, store_dir: Path) -> ToolExecutionContext:
    store_dir.mkdir(parents=True, exist_ok=True)
    # Wire the services the context-category tools need. Without them the registry
    # blocks the call, and a blocked tool legitimately has no preview — which would
    # report as "renders nothing" and be indistinguishable from a real bug.
    persona_service = PersonaHomeService(root_dir=store_dir / "personas")
    return ToolExecutionContext(
        workdir=workspace,
        session_workspace_root=workspace,
        session_key="tool-output-audit",
        provider_name="audit",
        model="audit",
        session_store=SessionStore(path=store_dir / "index.json"),
        transcript_store=TranscriptStore(root_dir=store_dir),
        providers={},
        # Full access so write tools execute rather than reporting a policy block —
        # the audit is about output shape, not about policy.
        policy=policy_for_task_mode("full-access", provider="openai-codex"),
        memory_service=MemoryService(MemoryStore(path=store_dir / "memory.json")),
        persona_service=persona_service,
        user_notes_service=UserNotesService(
            store=UserNotesStore(path=store_dir / "user_notes.json"),
            persona_service=persona_service,
        ),
    )


async def audit(*, offline: bool) -> list[dict]:
    renderable = rendered_preview_types()
    registry = ToolRegistry(policy=ToolPolicy())
    rows: list[dict] = []

    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp) / "workspace"
        workspace.mkdir()
        # A file to read/search so the repo-read tools have real content.
        (workspace / "README.md").write_text(
            "# Audit workspace\n\n" + "\n".join(f"line {i}" for i in range(1, 60)),
            encoding="utf-8",
        )
        (workspace / "audit_probe.txt").write_text("audit probe\n", encoding="utf-8")
        context = build_context(workspace, Path(tmp) / "store")

        for descriptor in registry.list_tools():
            tool_id = descriptor.id
            if tool_id not in FIXTURES:
                rows.append({"toolId": tool_id, "status": "no_fixture"})
                continue
            if offline and tool_id in NETWORK_TOOLS:
                rows.append({"toolId": tool_id, "status": "skipped_network"})
                continue

            arguments = dict(FIXTURES[tool_id])
            # files.rg / files.read fixtures point at the real repo, not the temp one.
            if tool_id in {"files.rg"}:
                arguments["path"] = str(REPO / "src" / "copenet" / "core" / "tools")
            try:
                result = await registry.execute(
                    ToolExecutionRequest(tool_id=tool_id, arguments=arguments), context
                )
            except Exception as exc:  # noqa: BLE001 — an audit must report, not abort
                rows.append({"toolId": tool_id, "status": "raised", "error": f"{type(exc).__name__}: {exc}"})
                continue

            body = result.body if result.body is not None else result.output
            body_chars = len(json.dumps(body, ensure_ascii=False, default=str)) if body is not None else 0
            preview = _preview_payload(tool_id, body)
            shown = preview_text(preview)
            preview_type = (preview or {}).get("type")
            resolved, how = resolve_client_preview(preview)
            if resolved is None:
                verdict = "nothing_to_show"
            elif how == "json_dump":
                # Renders, but as the envelope clipped to 500 chars rather than
                # the tool's output — the quietest of the failure modes.
                verdict = "json_dump_500"
            elif resolved not in renderable:
                verdict = "orphan_type"
            elif how == "sniffed":
                # Works today, but only because the client guesses from field
                # names. Rename a backend field and it silently degrades.
                verdict = "ok_by_sniffing"
            else:
                verdict = "ok"
            rows.append(
                {
                    "toolId": tool_id,
                    "status": "ok" if result.ok else "tool_error",
                    "error": result.error,
                    "summary": redact(result.summary),
                    "previewType": preview_type,
                    "resolvedType": resolved,
                    "resolvedVia": how,
                    "verdict": verdict,
                    "renderable": verdict in {"ok", "ok_by_sniffing"},
                    "bodyChars": body_chars,
                    "previewChars": len(shown),
                    "retention": round(len(shown) / body_chars, 3) if body_chars else None,
                    "sample": redact(shown[:400]),
                }
            )
    return rows


def report(rows: list[dict]) -> str:
    lines = ["# Tool output audit", ""]
    lines.append("| tool | preview | renderable | body | shown | kept |")
    lines.append("|---|---|---|---|---|---|")
    for row in rows:
        if row["status"] != "ok" and row["status"] != "tool_error":
            lines.append(f"| `{row['toolId']}` | — | — | — | — | {row['status']} |")
            continue
        kept = "—" if row["retention"] is None else f"{row['retention'] * 100:.0f}%"
        verdict = row["verdict"]
        flag = verdict if verdict.startswith("ok") else f"**{verdict}**"
        preview = row["resolvedType"] or "—"
        lines.append(
            f"| `{row['toolId']}` | {preview} | {flag} | {row['bodyChars']} | {row['previewChars']} | {kept} |"
        )
    lines.append("")
    problems = [r for r in rows if r.get("verdict") and not r["verdict"].startswith("ok")]
    if problems:
        lines.append("## Not rendered as intended")
        lines.append("")
        explain = {
            "json_dump_500": "no shape the client recognizes — shows the envelope JSON clipped at 500 chars",
            "orphan_type": "preview `type` has no renderer in ToolResultPreview — shows nothing",
            "nothing_to_show": "no preview at all — the inspector shows nothing",
        }
        for row in problems:
            lines.append(
                f"- `{row['toolId']}` (`{row['previewType'] or 'none'}`) — {explain.get(row['verdict'], row['verdict'])}"
            )
        lines.append("")
    sniffed = [r for r in rows if r.get("verdict") == "ok_by_sniffing"]
    if sniffed:
        lines.append("## Renders only because the client guesses the shape")
        lines.append("")
        for row in sniffed:
            lines.append(
                f"- `{row['toolId']}` — backend sends no `type`; the client infers "
                f"`{row['resolvedType']}` from field names. Renaming a field breaks it silently."
            )
        lines.append("")
    lossy = [
        r for r in rows
        if r.get("renderable") and r.get("retention") is not None and r["retention"] < 0.5 and r["bodyChars"] > 200
    ]
    if lossy:
        lines.append("## Keeps less than half the body — worth a look, not automatically wrong")
        lines.append("")
        lines.append(
            "A low number is fine when the projection *is* the useful view: a diff is the "
            "point of `files.write`, and `shell.exec` deliberately keeps stdout and drops "
            "its metadata. It is a problem when the dropped part is the answer — which is "
            "what `market.compare` did when it kept only ticker symbols."
        )
        lines.append("")
        for row in sorted(lossy, key=lambda r: r["retention"]):
            lines.append(
                f"- `{row['toolId']}` — keeps {row['retention'] * 100:.0f}% "
                f"({row['previewChars']} of {row['bodyChars']} chars)"
            )
        lines.append("")
    lines.append("## What each tool shows")
    lines.append("")
    for row in rows:
        if row.get("status") not in {"ok", "tool_error"}:
            continue
        lines.append(f"### `{row['toolId']}`")
        lines.append("")
        lines.append(f"{row['summary']}")
        lines.append("")
        lines.append("```")
        lines.append(row["sample"] or "(nothing)")
        lines.append("```")
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true", help="skip tools that reach the network")
    parser.add_argument("--json", action="store_true", help="emit raw rows instead of the markdown report")
    parser.add_argument("--out", type=Path, default=None, help="write the report to a file")
    args = parser.parse_args()

    rows = asyncio.run(audit(offline=args.offline))
    text = json.dumps(rows, indent=2, ensure_ascii=False) if args.json else report(rows)
    if args.out:
        args.out.write_text(text, encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        print(text)


if __name__ == "__main__":
    main()
