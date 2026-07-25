"""Dossier rendering — Phase 1 scope: single analyst, no reveal barrier/cross-exam yet.

The full 16-section dossier structure (design doc §10: bull/bear cases, Fleet
cross-examination, benchmark hurdle table, proposed thesis, etc.) requires the
dual-analyst stages Phase 3 builds. This is a smaller single-analyst version
that still keeps the same non-negotiable properties: every evidence item is
source-linked, calculations carry their inputs, and the evidence appendix is
never silently dropped even though there's no cross-exam to react to it yet.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .benchmarks import BenchmarkPlan
from .calculations import CalculationRecord
from .models import ResearchEvidenceItem


@dataclass(frozen=True)
class Dossier:
    subject_id: str
    company_name: str
    symbol: str
    generated_at: str
    benchmark_plan: BenchmarkPlan
    evidence: list[ResearchEvidenceItem]
    calculations: list[CalculationRecord]
    analyst_memo: str
    gathering_lane_stats: dict[str, Any] = field(default_factory=dict)

    def to_markdown(self) -> str:
        lines: list[str] = [
            f"# Research Lab Dossier — {self.company_name} ({self.symbol.upper()})",
            "",
            f"Generated: {self.generated_at}",
            (
                "**Phase 1 single-analyst pass — no reveal barrier, no cross-examination, "
                "no synthesis. Treat as a research draft, not a final investment verdict.**"
            ),
            "",
            "## Benchmark Plan",
            "",
            f"- Primary: {self.benchmark_plan.primary_benchmark}",
            f"- Sector: {self.benchmark_plan.sector_benchmark or 'unmapped'} "
            f"(confidence: {self.benchmark_plan.mapping_confidence}) — {self.benchmark_plan.rationale}",
        ]
        if self.benchmark_plan.peer_benchmarks:
            lines.append(f"- Peers: {', '.join(self.benchmark_plan.peer_benchmarks)}")
        lines.extend(["", "## Analyst Memo", "", self.analyst_memo.strip(), ""])

        if self.calculations:
            lines.append("## Calculations")
            lines.append("")
            for calc in self.calculations:
                inputs_str = ", ".join(f"{i['name']}={i['value']}" for i in calc.inputs)
                warn = f" ⚠ {'; '.join(calc.warnings)}" if calc.warnings else ""
                lines.append(f"- **{calc.formula_name}** = {calc.output_value:.4f} {calc.output_unit} ({inputs_str}){warn}")
            lines.append("")

        lines.append(f"## Evidence Appendix ({len(self.evidence)} items)")
        lines.append("")
        by_type: dict[str, int] = {}
        for item in self.evidence:
            by_type[item.source_type] = by_type.get(item.source_type, 0) + 1
        for source_type, count in sorted(by_type.items()):
            lines.append(f"- {source_type}: {count}")
        lines.append("")
        for item in self.evidence:
            warn = f" ⚠ {'; '.join(item.extraction_warnings)}" if item.extraction_warnings else ""
            url_part = f" — {item.source_url}" if item.source_url else ""
            lines.append(f"- `{item.evidence_id}` [{item.classification}] {item.source_title}{url_part}{warn}")

        if self.gathering_lane_stats:
            lines.extend(
                [
                    "",
                    "## Gathering Lane Stats",
                    "",
                    f"- Tool calls: {self.gathering_lane_stats.get('toolCallCount')}"
                    + (
                        " (over soft budget)"
                        if self.gathering_lane_stats.get("overBudget")
                        else ""
                    ),
                ]
            )
        return "\n".join(lines)


def build_dossier(
    *,
    subject_id: str,
    company_name: str,
    symbol: str,
    benchmark_plan: BenchmarkPlan,
    evidence: list[ResearchEvidenceItem],
    calculations: list[CalculationRecord],
    analyst_memo: str,
    gathering_lane_stats: dict[str, Any] | None = None,
) -> Dossier:
    return Dossier(
        subject_id=subject_id,
        company_name=company_name,
        symbol=symbol,
        generated_at=datetime.now(timezone.utc).isoformat(),
        benchmark_plan=benchmark_plan,
        evidence=evidence,
        calculations=calculations,
        analyst_memo=analyst_memo,
        gathering_lane_stats=gathering_lane_stats or {},
    )
