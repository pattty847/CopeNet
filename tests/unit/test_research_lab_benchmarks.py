"""Tests for research_lab/benchmarks.py: deterministic benchmark/sector resolution."""

from __future__ import annotations

import pytest

from copenet.core.research_lab import benchmarks


class _FakeTicker:
    def __init__(self, info: dict) -> None:
        self.info = info


def test_resolve_benchmarks_high_confidence_gics_mapping(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        benchmarks, "_fetch_sector_label", lambda symbol: "Technology"
    )
    plan = benchmarks.resolve_benchmarks("AAPL")
    assert plan.primary_benchmark == "VOO"
    assert plan.sector_benchmark == "XLK"
    assert plan.mapping_confidence == "high"


def test_resolve_benchmarks_unmapped_when_no_sector_data(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(benchmarks, "_fetch_sector_label", lambda symbol: None)
    plan = benchmarks.resolve_benchmarks("WEIRD")
    assert plan.sector_benchmark is None
    assert plan.mapping_confidence == "unmapped"
    assert "no sector data available" in plan.rationale


def test_resolve_benchmarks_low_confidence_for_unrecognized_sector_label(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(benchmarks, "_fetch_sector_label", lambda symbol: "Diversified Holding Conglomerate")
    plan = benchmarks.resolve_benchmarks("UHAL")
    assert plan.sector_benchmark is None
    assert plan.mapping_confidence == "low"
    assert plan.sector_label == "Diversified Holding Conglomerate"


def test_resolve_benchmarks_operator_override_is_always_high_confidence(monkeypatch: pytest.MonkeyPatch) -> None:
    # Even if sector lookup would fail, an explicit override must win and never
    # get silently overridden by the deterministic default.
    monkeypatch.setattr(benchmarks, "_fetch_sector_label", lambda symbol: None)
    plan = benchmarks.resolve_benchmarks(
        "UHAL", primary_override="VTI", sector_override="xli", peer_overrides=["psa", "exr"]
    )
    assert plan.primary_benchmark == "VTI"
    assert plan.sector_benchmark == "XLI"
    assert plan.peer_benchmarks == ["PSA", "EXR"]
    assert plan.mapping_confidence == "high"
    assert plan.rationale == "operator override"


def test_resolve_benchmarks_default_primary_is_voo() -> None:
    plan = benchmarks.resolve_benchmarks("AAPL", sector_override="XLK")
    assert plan.primary_benchmark == "VOO"
