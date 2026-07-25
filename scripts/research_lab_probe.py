"""Live Phase 1 probe for Research Lab: ticker -> evidence -> single analyst -> dossier.

No durability, no Fleet, no reveal barrier — proves the evidence model and
both lane-turn roles (gatherer + analyst) stand alone, the same way
`scripts/live_probe_matrix.py` proves the general runtime but against a
direct in-process Orchestrator (matching `copenet chat send`'s pattern), not
the WebSocket client, since Research Lab's coordinator will call the
orchestrator directly the same way.
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
import sys
from uuid import uuid4

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from copenet.core.coordination import LaneTurnSpec, run_lane_turn  # noqa: E402
from copenet.core.orchestrator import Orchestrator  # noqa: E402
from copenet.core.research_lab.benchmarks import resolve_benchmarks  # noqa: E402
from copenet.core.research_lab.calculations import calculate_cagr  # noqa: E402
from copenet.core.research_lab.dossier import build_dossier  # noqa: E402
from copenet.core.research_lab.evidence_builder import (  # noqa: E402
    build_evidence_from_edgar,
    build_evidence_from_fundamentals,
    render_evidence_snapshot,
    run_gathering_lane,
)
from copenet.core.research_lab.models import ResearchEvidenceItem  # noqa: E402


def _render_analyst_prompt(
    *, company_name: str, symbol: str, research_lens: str | None, persona: str, evidence_snapshot: str
) -> str:
    lens_line = f"Research focus: {research_lens}\n" if research_lens else ""
    return (
        f"You are an equity research analyst. Your lens: {persona}\n\n"
        f"Company: {company_name} ({symbol.upper()})\n"
        f"{lens_line}\n"
        "Below is a frozen evidence corpus gathered by a separate research pass. Analyze it — "
        "do not fetch new sources unless something material is clearly missing, and say so "
        "explicitly if it is. Give: business understanding, financial health read, valuation "
        "view, and your investment thesis. Every conclusion should trace back to a specific "
        "evidence id above or be labeled an explicit assumption, not asserted as fact.\n\n"
        f"{evidence_snapshot}"
    )


def _cagr_from_fundamentals(evidence: list[ResearchEvidenceItem]):
    """Best-effort revenue CAGR across whatever annual fundamentals evidence
    is present — a small deterministic proof point for calculations.py, not
    a complete Phase 3 calculation suite."""
    revenue_rows = sorted(
        (item for item in evidence if item.source_title.endswith("annual revenue") and item.normalized_value),
        key=lambda item: item.reporting_period or "",
    )
    if len(revenue_rows) < 2:
        return None
    start, end = revenue_rows[0], revenue_rows[-1]
    try:
        start_year = int((start.reporting_period or "")[:4])
        end_year = int((end.reporting_period or "")[:4])
    except ValueError:
        return None
    periods = end_year - start_year
    if periods <= 0 or start.normalized_value is None or end.normalized_value is None:
        return None
    return calculate_cagr(
        start_value=start.normalized_value,
        end_value=end.normalized_value,
        periods=periods,
        start_source_id=start.evidence_id,
        end_source_id=end.evidence_id,
    )


async def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Research Lab Phase 1 pipeline live against one ticker.")
    parser.add_argument("symbol")
    parser.add_argument("--company-name", default=None, help="Defaults to the symbol if omitted.")
    parser.add_argument("--research-lens", default=None)
    parser.add_argument("--gather-provider", default="openai-codex")
    parser.add_argument("--gather-model", default="gpt-5.5")
    parser.add_argument("--analyst-provider", default="claude-cli")
    parser.add_argument("--analyst-model", default=None)
    parser.add_argument(
        "--persona",
        default="a valuation-discipline skeptic focused on capital intensity and margin durability",
    )
    parser.add_argument("--output", default=None, help="Write the rendered dossier markdown to this path.")
    args = parser.parse_args()

    symbol = args.symbol.strip().upper()
    company_name = args.company_name or symbol
    parent_key = f"research-probe-{uuid4().hex[:10]}"

    print(f"[research-lab-probe] {company_name} ({symbol}) — parent_key={parent_key}")
    orchestrator = Orchestrator()

    print("[stage] resolving benchmarks...")
    benchmark_plan = resolve_benchmarks(symbol)
    print(f"  -> primary={benchmark_plan.primary_benchmark} sector={benchmark_plan.sector_benchmark} "
          f"({benchmark_plan.mapping_confidence}) — {benchmark_plan.rationale}")

    print("[stage] deterministic evidence (edgar insider/8-K sweep + fundamentals)...")
    edgar_evidence = await build_evidence_from_edgar(symbol, subject_id=symbol)
    fundamentals_evidence = await build_evidence_from_fundamentals(symbol, subject_id=symbol)
    print(f"  -> {len(edgar_evidence)} filing items, {len(fundamentals_evidence)} fundamentals items")

    print(f"[stage] bounded gathering lane ({args.gather_provider}/{args.gather_model})...")
    gathering_result = await run_gathering_lane(
        orchestrator,
        subject_id=symbol,
        symbol=symbol,
        company_name=company_name,
        research_lens=args.research_lens,
        parent_key=parent_key,
        provider=args.gather_provider,
        model=args.gather_model,
    )
    print(
        f"  -> {gathering_result.tool_call_count} tool calls "
        f"({'OVER soft budget' if gathering_result.over_budget else 'within soft budget'}), "
        f"{len(gathering_result.evidence)} evidence items normalized"
    )

    all_evidence = edgar_evidence + fundamentals_evidence + gathering_result.evidence
    calculations = []
    cagr = _cagr_from_fundamentals(all_evidence)
    if cagr is not None:
        calculations.append(cagr)
        print(f"  -> revenue CAGR calculated: {cagr.output_value:.2%}")

    print(f"[stage] single analyst pass ({args.analyst_provider}/{args.analyst_model or '(default)'})...")
    evidence_snapshot = render_evidence_snapshot(all_evidence)
    analyst_prompt = _render_analyst_prompt(
        company_name=company_name,
        symbol=symbol,
        research_lens=args.research_lens,
        persona=args.persona,
        evidence_snapshot=evidence_snapshot,
    )
    analyst_session_key = f"{parent_key}-analyst"
    orchestrator._session_store.create_session(
        session_key=analyst_session_key,
        provider=args.analyst_provider,
        model=args.analyst_model,
        title=f"Research Lab · {company_name} · analyst",
        system_prompt_id="default",
        task_prompt_id="none",
        persona_id="default",
        persona_privacy_tier="private",
        workspace_root=None,
        session_type="research_lane",
        parent_session_key=parent_key,
        participant_id="analyst",
    )
    analyst_result = await run_lane_turn(
        orchestrator,
        LaneTurnSpec(
            session_key=analyst_session_key,
            provider=args.analyst_provider,
            model=args.analyst_model,
            prompt=analyst_prompt,
        ),
    )
    final_text = analyst_result["content"]
    print(f"  -> analyst run {analyst_result['runId']}, {len(final_text)} chars")

    dossier = build_dossier(
        subject_id=symbol,
        company_name=company_name,
        symbol=symbol,
        benchmark_plan=benchmark_plan,
        evidence=all_evidence,
        calculations=calculations,
        analyst_memo=final_text,
        gathering_lane_stats={
            "toolCallCount": gathering_result.tool_call_count,
            "overBudget": gathering_result.over_budget,
        },
    )
    markdown = dossier.to_markdown()
    if args.output:
        Path(args.output).write_text(markdown, encoding="utf-8")
        print(f"[done] dossier written to {args.output}")
    else:
        print("\n" + markdown)


if __name__ == "__main__":
    asyncio.run(main())
