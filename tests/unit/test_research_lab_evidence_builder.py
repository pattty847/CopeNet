"""Tests for research_lab/evidence_builder.py: deterministic wrappers + gathering lane."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from copenet.core.market.models import EvidenceItem, TickerEvidencePayload
from copenet.core.research_lab import evidence_builder
from copenet.core.research_lab.evidence_builder import (
    GATHERING_LANE_SOFT_BUDGET,
    build_evidence_from_edgar,
    build_evidence_from_fundamentals,
    render_evidence_snapshot,
    run_gathering_lane,
)
from copenet.core.runtime.runs import RunRecord, RunStore
from copenet.core.sessions import SessionStore


class FakeOrchestrator:
    """As in test_lane_runner.py: the streaming `emit` only carries lightweight
    `toolExecution` receipts; full tool bodies land on the completed RunRecord,
    which `run_lane_turn` reads back via `_run_store.get()`."""

    def __init__(self, root: Path, *, tool_call_count: int) -> None:
        self._session_store = SessionStore(path=root / "index.json")
        self._run_store = RunStore(root_dir=root / "runs")
        self.tool_call_count = tool_call_count

    async def send_chat(self, request, emit) -> dict[str, Any]:
        tool_results = []
        for index in range(self.tool_call_count):
            await emit(
                {
                    "state": "tool_result",
                    "toolExecution": {"toolId": "web.fetch", "ok": True, "summary": "s", "preview": None},
                }
            )
            tool_results.append(
                {
                    "toolId": "web.fetch",
                    "body": {
                        "url": f"https://example.com/{index}",
                        "title": f"Page {index}",
                        "text": "body text",
                        "excerpt": "an excerpt",
                        "wordCount": 100,
                    },
                }
            )
        await emit(
            {
                "state": "final",
                "message": {"content": "I looked at a bunch of pages and this is unrelated commentary I wrote."},
            }
        )
        self._run_store.create(
            RunRecord(
                run_id="run-gather-1",
                session_key=request.session_key,
                provider=request.provider,
                model=request.model,
                status="ok",
                user_message=request.message,
                tool_execution_mode="responses",
                will_attempt_tool_loop=True,
                tool_results=tool_results,
            )
        )
        return {"runId": "run-gather-1"}


@pytest.mark.asyncio
async def test_build_evidence_from_edgar_normalizes_source_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = TickerEvidencePayload(
        symbol="UHAL",
        evidence=[
            EvidenceItem(
                type="8-K",
                symbol="UHAL",
                headline="Material event",
                source="SEC 8-K",
                tone="flat",
                url="https://www.sec.gov/Archives/edgar/data/4457/000119312526241898/",
                t=1750000000,
                value=None,
            )
        ],
        events=[],
        as_of="2026-07-01",
        refreshed=False,
    )

    async def fake_fetch_ticker_evidence(symbol: str, **kwargs: Any):
        return payload

    monkeypatch.setattr(evidence_builder.edgar, "fetch_ticker_evidence", fake_fetch_ticker_evidence)

    items = await build_evidence_from_edgar("UHAL", subject_id="uhal-1")

    assert len(items) == 1
    item = items[0]
    assert item.source_type == "sec_filing"
    assert item.accession_number == "000119312526241898"
    assert item.classification == "reported"
    assert item.retrieved_at  # always stamped, not left None
    assert item.extraction_warnings == []


@pytest.mark.asyncio
async def test_build_evidence_from_edgar_flags_unparseable_sec_url(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = TickerEvidencePayload(
        symbol="UHAL",
        evidence=[
            EvidenceItem(
                type="News", symbol="UHAL", headline="x", source="s", tone="flat",
                url="https://www.sec.gov/some/odd/path/without/an/accession",
            )
        ],
        events=[], as_of="2026-07-01", refreshed=False,
    )

    async def fake_fetch_ticker_evidence(symbol: str, **kwargs: Any):
        return payload

    monkeypatch.setattr(evidence_builder.edgar, "fetch_ticker_evidence", fake_fetch_ticker_evidence)
    items = await build_evidence_from_edgar("UHAL", subject_id="uhal-1")

    assert items[0].accession_number is None
    assert "accession number not resolvable" in items[0].extraction_warnings[0]


@pytest.mark.asyncio
async def test_build_evidence_from_fundamentals_handles_missing_data(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_fetch_fundamentals(symbol: str, **kwargs: Any):
        return None

    monkeypatch.setattr(evidence_builder.edgar, "fetch_fundamentals", fake_fetch_fundamentals)
    items = await build_evidence_from_fundamentals("UHAL", subject_id="uhal-1")
    assert items == []  # None means "unavailable", not zero rows fabricated


@pytest.mark.asyncio
async def test_build_evidence_from_fundamentals_normalizes_numeric_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_fetch_fundamentals(symbol: str, **kwargs: Any):
        return {
            "entityName": "U-HAUL HOLDING COMPANY",
            "sourceForm": "10-K",
            "revenueQuarterly": [{"date": "2025-06-30", "value": "232056000"}],
            "epsQuarterly": [],
            "revenueAnnual": [],
            "epsAnnual": [],
        }

    monkeypatch.setattr(evidence_builder.edgar, "fetch_fundamentals", fake_fetch_fundamentals)
    items = await build_evidence_from_fundamentals("UHAL", subject_id="uhal-1")

    assert len(items) == 1
    assert items[0].normalized_value == 232056000.0
    assert items[0].accession_number is None
    assert items[0].source_type == "fundamentals_xbrl"


@pytest.mark.asyncio
async def test_run_gathering_lane_discards_prose_keeps_only_typed_evidence(tmp_path: Path) -> None:
    orchestrator = FakeOrchestrator(tmp_path, tool_call_count=3)

    result = await run_gathering_lane(
        orchestrator,
        subject_id="uhal-1",
        symbol="UHAL",
        company_name="U-Haul Holding Company",
        research_lens=None,
        parent_key="probe-1",
        provider="openai-codex",
        model="gpt-5.5",
    )

    assert result.tool_call_count == 3
    assert result.over_budget is False
    assert len(result.evidence) == 3
    for item in result.evidence:
        assert item.source_type == "web_page"
        assert item.source_url and item.source_url.startswith("https://example.com/")
    # the gathering lane's own final "commentary" text must never appear anywhere in evidence
    rendered = render_evidence_snapshot(result.evidence)
    assert "unrelated commentary" not in rendered


@pytest.mark.asyncio
async def test_run_gathering_lane_flags_over_budget(tmp_path: Path) -> None:
    orchestrator = FakeOrchestrator(tmp_path, tool_call_count=GATHERING_LANE_SOFT_BUDGET + 1)

    result = await run_gathering_lane(
        orchestrator,
        subject_id="uhal-1",
        symbol="UHAL",
        company_name="U-Haul Holding Company",
        research_lens="why did margins compress",
        parent_key="probe-2",
        provider="openai-codex",
        model="gpt-5.5",
    )

    assert result.over_budget is True


def test_render_evidence_snapshot_only_contains_structured_fields() -> None:
    from copenet.core.research_lab.models import ResearchEvidenceItem

    item = ResearchEvidenceItem(
        evidence_id="ev-1",
        subject_id="s1",
        source_title="Example filing",
        source_type="sec_filing",
        source_url="https://sec.gov/x",
        accession_number="123",
        publisher="SEC",
        retrieved_at="2026-01-01T00:00:00Z",
        published_at=None,
        reporting_period="2025-Q4",
        raw_value="1000",
        normalized_value=1000.0,
        unit="usd",
        classification="reported",
        freshness="current",
        extraction_method="test",
        extraction_context="why this was fetched",
    )
    rendered = render_evidence_snapshot([item])
    assert "ev-1" in rendered
    assert "sec_filing" in rendered
    assert "why this was fetched" in rendered
    assert "[EVIDENCE CORPUS]" in rendered and "[END EVIDENCE CORPUS]" in rendered
