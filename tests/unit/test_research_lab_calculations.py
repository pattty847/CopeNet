"""Tests for research_lab/calculations.py: deterministic math with provenance."""

from __future__ import annotations

from copenet.core.research_lab.calculations import calculate_benchmark_hurdle, calculate_cagr, calculate_margin


def test_calculate_cagr_positive_growth() -> None:
    record = calculate_cagr(start_value=100, end_value=200, periods=1, start_source_id="ev-a", end_source_id="ev-b")
    assert record.output_value == 1.0  # doubled in one year = 100% CAGR
    assert record.warnings == []
    assert record.inputs[0]["source_or_assumption_id"] == "ev-a"


def test_calculate_cagr_non_positive_start_value_warns_never_fabricates() -> None:
    record = calculate_cagr(start_value=0, end_value=200, periods=1, start_source_id="ev-a", end_source_id="ev-b")
    assert record.output_value == 0.0
    assert "undefined" in record.warnings[0]


def test_calculate_margin_divides_and_records_sources() -> None:
    record = calculate_margin(
        numerator=25, denominator=100, margin_name="operating_margin",
        numerator_source_id="ev-op", denominator_source_id="ev-rev",
    )
    assert record.output_value == 0.25
    assert record.formula_name == "operating_margin"


def test_calculate_margin_zero_denominator_warns_never_divides_by_zero() -> None:
    record = calculate_margin(
        numerator=25, denominator=0, margin_name="operating_margin",
        numerator_source_id="ev-op", denominator_source_id="ev-rev",
    )
    assert record.output_value == 0.0
    assert "zero" in record.warnings[0]


def test_calculate_benchmark_hurdle_is_a_transparent_gap_not_a_score() -> None:
    record = calculate_benchmark_hurdle(
        subject_return=0.12, benchmark_return=0.08,
        subject_label="uhal", benchmark_label="voo",
        subject_source_id="calc-1", benchmark_source_id="calc-2",
    )
    assert round(record.output_value, 2) == 0.04
    assert record.formula_name == "benchmark_hurdle_gap"
