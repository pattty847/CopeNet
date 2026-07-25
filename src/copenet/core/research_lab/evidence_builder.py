"""Evidence Builder: deterministic wrappers + bounded GPT gathering lane.

Two complementary sources feed the same frozen evidence snapshot, per the
2026-07-24 Stage 2 redesign (see ~/.claude/plans/hazy-kindling-stardust.md):

1. Deterministic wrapper calls (`edgar.py`) for structured numeric data an
   LLM wouldn't reliably surface cleanly — called directly, bypassing the
   LLM tool-calling loop entirely.
2. A bounded, coordinator-triggered GPT research lane (`run_gathering_lane`)
   for adaptive web/market research, reusing `core/coordination/lane_runner`.
   Every tool call/result pair it produces gets normalized into a
   `ResearchEvidenceItem` here — the lane's own prose/reasoning is discarded.
   Zero interpretive commentary reaches downstream consumers of this
   module's output; that boundary is what keeps Stage 4's two analysts
   independent of the gatherer's framing.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from copenet.core.coordination import LaneTurnSpec, create_lane_sessions, run_lane_turn
from copenet.core.market import edgar

from .models import ResearchEvidenceItem

# A Research-Lab-specific soft ceiling, well under the harness's general
# MAX_TOOL_STEPS=100. Not hard-enforced (V1 is a soft cost guard per the
# locked decision) — the gathering lane's prompt asks the model to wrap up
# around this budget, and GatheringLaneResult.over_budget flags it after the
# fact so the coordinator can log/surface it, not silently absorb it.
GATHERING_LANE_SOFT_BUDGET = 25

_ACCESSION_RE = re.compile(r"Archives/edgar/data/\d+/(\d{18}|\d{10}-\d{2}-\d{6})")
_PRIMARY_SOURCE_HINTS = ("sec.gov", "investors.", "ir.")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_evidence_id() -> str:
    return f"ev-{uuid4().hex[:12]}"


def _parse_accession_number(url: str | None) -> tuple[str | None, str | None]:
    """Best-effort accession-number extraction from an EDGAR URL.

    Returns (accession_number, warning). A non-EDGAR URL isn't a warning
    condition — accession numbers only apply to SEC filings.
    """
    if not url:
        return None, None
    match = _ACCESSION_RE.search(url)
    if match:
        return match.group(1), None
    if "sec.gov" in url:
        return None, "accession number not resolvable from source URL"
    return None, None


def _source_label(url: str | None) -> str:
    if url and any(hint in url for hint in _PRIMARY_SOURCE_HINTS):
        return "primary source"
    return "secondary source (general web) — not a primary filing"


# -- 1. Deterministic wrapper calls ---------------------------------------------


async def build_evidence_from_edgar(
    symbol: str, *, subject_id: str, snapshot_version: int = 1
) -> list[ResearchEvidenceItem]:
    """Deterministic evidence from CopeTech-Edgar's insider/8-K/144 sweep."""
    payload = await edgar.fetch_ticker_evidence(symbol)
    items: list[ResearchEvidenceItem] = []
    retrieved_at = _now()
    for row in payload.evidence:
        accession_number, warning = _parse_accession_number(row.url)
        published_at = (
            datetime.fromtimestamp(row.t, tz=timezone.utc).isoformat() if row.t is not None else None
        )
        items.append(
            ResearchEvidenceItem(
                evidence_id=_new_evidence_id(),
                subject_id=subject_id,
                source_title=f"{row.type}: {row.headline}",
                source_type="sec_filing",
                source_url=row.url,
                accession_number=accession_number,
                publisher=row.source,
                retrieved_at=retrieved_at,
                published_at=published_at,
                reporting_period=None,
                raw_value=row.headline,
                normalized_value=row.value,
                unit="usd" if row.value is not None else None,
                classification="reported",
                freshness="current",
                extraction_method="edgar.fetch_ticker_evidence",
                extraction_context=f"insider/8-K/144 sweep, filing type={row.type}",
                extraction_warnings=[warning] if warning else [],
                snapshot_version=snapshot_version,
            )
        )
    return items


async def build_evidence_from_fundamentals(
    symbol: str, *, subject_id: str, snapshot_version: int = 1
) -> list[ResearchEvidenceItem]:
    """Deterministic evidence from CopeTech-Edgar's quarterly/annual XBRL fundamentals.

    No accession number is available at this layer — always None, a known
    V1 limitation (a real fix belongs upstream in CopeTech-Edgar, not here).
    """
    fundamentals = await edgar.fetch_fundamentals(symbol)
    items: list[ResearchEvidenceItem] = []
    if not fundamentals:
        return items
    retrieved_at = _now()
    metric_series = {
        "revenueQuarterly": ("revenue", "quarterly"),
        "epsQuarterly": ("EPS", "quarterly"),
        "revenueAnnual": ("revenue", "annual"),
        "epsAnnual": ("EPS", "annual"),
    }
    for key, (metric_name, period_kind) in metric_series.items():
        rows = fundamentals.get(key)
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            raw_value = row.get("value")
            try:
                normalized_value = float(raw_value) if raw_value is not None else None
            except (TypeError, ValueError):
                normalized_value = None
            items.append(
                ResearchEvidenceItem(
                    evidence_id=_new_evidence_id(),
                    subject_id=subject_id,
                    source_title=f"{symbol.upper()} {period_kind} {metric_name}",
                    source_type="fundamentals_xbrl",
                    source_url=None,
                    accession_number=None,
                    publisher=str(fundamentals.get("entityName") or "SEC XBRL (via CopeTech-Edgar)"),
                    retrieved_at=retrieved_at,
                    published_at=None,
                    reporting_period=str(row.get("date") or "") or None,
                    raw_value=str(raw_value) if raw_value is not None else None,
                    normalized_value=normalized_value,
                    unit=None,
                    classification="reported",
                    freshness="current",
                    extraction_method="edgar.fetch_fundamentals",
                    extraction_context=(
                        f"source form {fundamentals.get('sourceForm')!r} — no accession number "
                        "available at this layer (known V1 limitation)"
                    ),
                    extraction_warnings=[],
                    snapshot_version=snapshot_version,
                )
            )
    return items


# -- 2. Bounded GPT gathering lane -----------------------------------------------


@dataclass(frozen=True)
class GatheringLaneResult:
    evidence: list[ResearchEvidenceItem]
    tool_call_count: int
    over_budget: bool
    lane_session_key: str
    run_id: str | None


def _render_gatherer_prompt(*, company_name: str, symbol: str, research_lens: str | None) -> str:
    """Role-framing built into the message content, matching Fleet's
    `_render_updates` convention exactly — no new system_prompt_id/preset
    file, just an explicit instruction block ahead of the actual task."""
    lens_line = f"\nResearch lens (shapes attention, does not narrow collection): {research_lens}\n" if research_lens else ""
    return (
        "You are a research gatherer for CopeNet's Research Lab. Your ONLY job is to gather "
        "sourced facts — you do not analyze, conclude, or recommend anything. Another pair of "
        "analysts will do that later from what you collect; do not do their job for them.\n\n"
        f"Company: {company_name} ({symbol.upper()})\n"
        f"{lens_line}"
        "\nUse web.search and web.fetch (and market.ticker/market.evidence/market.compare where "
        "useful) to gather: SEC filings and annual/quarterly reports, earnings releases and "
        "investor presentations, segment/geography breakdowns, industry structure, competitor "
        "data, and credible third-party analysis. Fetch primary sources over opinion pieces "
        "when both are available.\n\n"
        f"You have a soft budget of roughly {GATHERING_LANE_SOFT_BUDGET} tool calls — once you've "
        "gathered a reasonably broad, well-sourced picture, stop searching. Do not editorialize "
        "in your final reply: just briefly confirm what you looked at. Do not state conclusions, "
        "ratings, or opinions about the company — that is explicitly not your job."
    )


def _normalize_gathering_tool_result(
    tool_result: dict[str, Any], *, subject_id: str, snapshot_version: int
) -> ResearchEvidenceItem | None:
    """Normalize one tool call/result pair from the gathering lane into a
    ResearchEvidenceItem. Only the typed fields below survive — any prose the
    lane wrote about the result separately is never consulted here."""
    tool_id = str(tool_result.get("toolId") or "")
    body = tool_result.get("body")
    if not isinstance(body, dict):
        return None
    retrieved_at = _now()

    if tool_id == "web.fetch":
        url = body.get("url")
        return ResearchEvidenceItem(
            evidence_id=_new_evidence_id(),
            subject_id=subject_id,
            source_title=str(body.get("title") or url or "fetched page"),
            source_type="web_page",
            source_url=url,
            accession_number=_parse_accession_number(url)[0],
            publisher=None,
            retrieved_at=retrieved_at,
            published_at=None,
            reporting_period=None,
            raw_value=str(body.get("excerpt") or "")[:500] or None,
            normalized_value=None,
            unit=None,
            classification="reported",
            freshness="current",
            extraction_method="research_gatherer:web.fetch",
            extraction_context=f"{_source_label(url)}; {body.get('wordCount')} words fetched",
            extraction_warnings=[],
            snapshot_version=snapshot_version,
        )

    if tool_id == "web.search":
        results = body.get("results")
        top = [r for r in results if isinstance(r, dict)][:5] if isinstance(results, list) else []
        return ResearchEvidenceItem(
            evidence_id=_new_evidence_id(),
            subject_id=subject_id,
            source_title=f"search: {body.get('query')}",
            source_type="search_result",
            source_url=None,
            accession_number=None,
            publisher=str(body.get("source") or None) if body.get("source") else None,
            retrieved_at=retrieved_at,
            published_at=None,
            reporting_period=None,
            raw_value=json.dumps([{"title": r.get("title"), "url": r.get("url")} for r in top], ensure_ascii=False),
            normalized_value=None,
            unit=None,
            classification="reported",
            freshness="current",
            extraction_method="research_gatherer:web.search",
            extraction_context=f"query used to find sources, not a fact itself; {len(top)} results kept",
            extraction_warnings=[],
            snapshot_version=snapshot_version,
        )

    if tool_id.startswith("market."):
        return ResearchEvidenceItem(
            evidence_id=_new_evidence_id(),
            subject_id=subject_id,
            source_title=f"{tool_id} result",
            source_type="market_data",
            source_url=None,
            accession_number=None,
            publisher="yfinance/CopeTech-Edgar (via market.* tool)",
            retrieved_at=retrieved_at,
            published_at=None,
            reporting_period=None,
            raw_value=json.dumps(body, ensure_ascii=False, default=str)[:2000],
            normalized_value=None,
            unit=None,
            classification="reported",
            freshness="current",
            extraction_method=f"research_gatherer:{tool_id}",
            extraction_context="gathering-lane market tool call",
            extraction_warnings=[],
            snapshot_version=snapshot_version,
        )

    return None


async def run_gathering_lane(
    orchestrator: Any,
    *,
    subject_id: str,
    symbol: str,
    company_name: str,
    research_lens: str | None,
    parent_key: str,
    provider: str = "openai-codex",
    model: str | None = None,
    snapshot_version: int = 1,
) -> GatheringLaneResult:
    """Run the bounded GPT research lane and return its findings as typed
    evidence only — never its own prose/interpretation."""
    participants = create_lane_sessions(
        orchestrator,
        parent_key=parent_key,
        session_type="research_lane",
        title_prefix=f"Research Lab · {company_name}",
        participant_specs={"gatherer": {"provider": provider, "model": model}},
        workspace_root=None,
    )
    lane_session_key = participants["gatherer"]["laneSessionKey"]

    prompt = _render_gatherer_prompt(company_name=company_name, symbol=symbol, research_lens=research_lens)
    result = await run_lane_turn(
        orchestrator,
        LaneTurnSpec(
            session_key=lane_session_key,
            provider=provider,
            model=model,
            prompt=prompt,
        ),
    )

    evidence: list[ResearchEvidenceItem] = []
    for tool_result in result["toolResults"]:
        item = _normalize_gathering_tool_result(
            tool_result, subject_id=subject_id, snapshot_version=snapshot_version
        )
        if item is not None:
            evidence.append(item)

    return GatheringLaneResult(
        evidence=evidence,
        tool_call_count=result["toolCallCount"],
        over_budget=result["toolCallCount"] > GATHERING_LANE_SOFT_BUDGET,
        lane_session_key=lane_session_key,
        run_id=result.get("runId"),
    )


def render_evidence_snapshot(evidence: list[ResearchEvidenceItem]) -> str:
    """Render the frozen evidence corpus as plain text for a Stage 4 analyst
    lane's prompt. Every item's source/classification/context is visible;
    nothing here is interpretation — this is the shared factual substrate
    both analysts see identically, which is what keeps their judgments
    independent of each other and of the gathering lane."""
    lines = ["[EVIDENCE CORPUS]"]
    for item in evidence:
        lines.extend(
            [
                f"--- {item.evidence_id} ---",
                f"Source: {item.source_title} ({item.source_type}, {item.classification})",
                f"URL: {item.source_url or 'n/a'}",
                f"Value: {item.raw_value or item.normalized_value or 'n/a'}",
                f"Reporting period: {item.reporting_period or 'n/a'}",
                f"Context: {item.extraction_context or 'n/a'}",
            ]
        )
    lines.append("[END EVIDENCE CORPUS]")
    return "\n".join(lines)
