"""Evidence / claim / calculation / conflict data model for Research Lab.

Distinct from `core/market/models.py::EvidenceItem` — that one is chart-marker
oriented (no accession number, no claim linkage). These carry the provenance
and claim-typing discipline design doc §8 requires: every material report
claim traces to recorded evidence or an explicit assumption, never silently
invented precision.

Plain snake_case dataclasses for now — no `to_wire()` camelCase conversion
yet, since nothing in Phase 1 serializes these to a frontend. That convention
(matching core/market/models.py's `_to_wire`) belongs to Phase 4's RPC layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

ClaimClass = Literal[
    "reported_fact",
    "calculated_metric",
    "explicit_assumption",
    "analyst_interpretation",
    "unresolved_claim",
]
EvidenceClassification = Literal["reported", "calculated", "estimated"]
Freshness = Literal["current", "stale", "unknown"]
Materiality = Literal["high", "medium", "low"]
Confidence = Literal["high", "medium", "low"]


@dataclass(frozen=True)
class ResearchEvidenceItem:
    """One sourced fact. `extraction_context` is factual traceability metadata
    only (what section, why fetched) — never interpretation. Interpretation
    belongs in a ClaimRecord with producer="gpt_analyst"/"claude_analyst"."""

    evidence_id: str
    subject_id: str
    source_title: str
    source_type: Literal["sec_filing", "fundamentals_xbrl", "web_page", "search_result", "market_data"]
    source_url: str | None
    accession_number: str | None
    publisher: str | None
    retrieved_at: str
    published_at: str | None
    reporting_period: str | None
    raw_value: str | None
    normalized_value: float | None
    unit: str | None
    classification: EvidenceClassification
    freshness: Freshness
    extraction_method: str
    extraction_context: str | None = None
    extraction_warnings: list[str] = field(default_factory=list)
    snapshot_version: int = 1


@dataclass(frozen=True)
class ClaimRecord:
    claim_id: str
    text: str
    claim_class: ClaimClass
    supporting_evidence_ids: list[str]
    contradicting_evidence_ids: list[str]
    producer: str  # "deterministic" | "gpt_analyst" | "claude_analyst"
    confidence: Confidence
    freshness: Freshness
    unresolved_limitations: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CalculationRecord:
    calculation_id: str
    formula_name: str
    formula_version: str
    inputs: list[dict[str, Any]]  # [{"name", "value", "unit", "source_or_assumption_id"}]
    output_value: float
    output_unit: str
    computed_at: str
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ConflictRecord:
    conflict_id: str
    evidence_ids: list[str]
    likely_reason: str | None
    materiality: Materiality
    resolution_status: Literal["unresolved", "resolved", "acknowledged"]


@dataclass(frozen=True)
class EvidenceRequest:
    """Stage 5's structured evidence-request shape (design doc §7), plus
    round tracking for the bounded supplement loop."""

    request_id: str
    claim: str
    reason: str
    requested_source_type: str
    materiality: Materiality
    would_change: str
    requested_by: str  # "gpt_analyst" | "claude_analyst"
    round_index: int
