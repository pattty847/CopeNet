"""Tests for research_lab/dossier.py: single-analyst Phase 1 dossier rendering."""

from __future__ import annotations

from copenet.core.research_lab.benchmarks import BenchmarkPlan
from copenet.core.research_lab.calculations import calculate_cagr
from copenet.core.research_lab.dossier import build_dossier
from copenet.core.research_lab.models import ResearchEvidenceItem


def _evidence_item(evidence_id: str, *, warnings: list[str] | None = None) -> ResearchEvidenceItem:
    return ResearchEvidenceItem(
        evidence_id=evidence_id,
        subject_id="uhal",
        source_title="Some filing",
        source_type="sec_filing",
        source_url="https://sec.gov/x",
        accession_number=None,
        publisher="SEC",
        retrieved_at="2026-01-01T00:00:00Z",
        published_at=None,
        reporting_period="2025-Q4",
        raw_value="100",
        normalized_value=100.0,
        unit="usd",
        classification="reported",
        freshness="current",
        extraction_method="test",
        extraction_warnings=warnings or [],
    )


def test_dossier_renders_all_sections_and_flags_phase1_scope() -> None:
    plan = BenchmarkPlan(primary_benchmark="VOO", sector_benchmark="XLI", sector_label="Industrials")
    calc = calculate_cagr(start_value=100, end_value=150, periods=2, start_source_id="ev-1", end_source_id="ev-2")
    dossier = build_dossier(
        subject_id="uhal",
        company_name="U-Haul Holding Company",
        symbol="UHAL",
        benchmark_plan=plan,
        evidence=[_evidence_item("ev-1"), _evidence_item("ev-2", warnings=["stale"])],
        calculations=[calc],
        analyst_memo="This is the analyst's memo body.",
        gathering_lane_stats={"toolCallCount": 15, "overBudget": False},
    )
    markdown = dossier.to_markdown()

    assert "no reveal barrier, no cross-examination" in markdown
    assert "VOO" in markdown and "XLI" in markdown
    assert "This is the analyst's memo body." in markdown
    assert "ev-1" in markdown and "ev-2" in markdown
    assert "⚠ stale" in markdown
    assert "Evidence Appendix (2 items)" in markdown
    assert "cagr" in markdown
    assert "Tool calls: 15" in markdown


def test_dossier_handles_empty_evidence_and_calculations_without_crashing() -> None:
    plan = BenchmarkPlan(primary_benchmark="VOO", sector_benchmark=None, mapping_confidence="unmapped")
    dossier = build_dossier(
        subject_id="x", company_name="X Corp", symbol="X",
        benchmark_plan=plan, evidence=[], calculations=[], analyst_memo="memo",
    )
    markdown = dossier.to_markdown()
    assert "Evidence Appendix (0 items)" in markdown
    assert "unmapped" in markdown
