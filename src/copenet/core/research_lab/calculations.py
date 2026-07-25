"""Deterministic financial calculations with full input/source provenance.

Design doc §8.3: every derived value records its formula, inputs (each with a
source-or-assumption id), output, and warnings — models may select, challenge,
and explain assumptions, but the arithmetic itself is deterministic code, not
LLM-computed. Phase 1 scope: CAGR, margins, and the benchmark hurdle table.
Full DCF/reverse-DCF is deferred per the plan (a bigger, assumption-heavy
calculation better suited to Phase 3 once real analyst judgment can supply
the growth/discount-rate assumptions it needs).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from .models import CalculationRecord

FORMULA_VERSION = "1"


def _new_calculation_id() -> str:
    return f"calc-{uuid4().hex[:12]}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def calculate_cagr(
    *, start_value: float, end_value: float, periods: float, start_source_id: str, end_source_id: str
) -> CalculationRecord:
    """Compound annual growth rate over `periods` years. Returns a record with
    output_value=0.0 and a warning (never a fabricated number) when the math
    is undefined — a negative or zero start value has no real CAGR."""
    warnings: list[str] = []
    if start_value <= 0 or periods <= 0:
        warnings.append("CAGR undefined for a non-positive start value or period count")
        output_value = 0.0
    else:
        output_value = (end_value / start_value) ** (1 / periods) - 1
    return CalculationRecord(
        calculation_id=_new_calculation_id(),
        formula_name="cagr",
        formula_version=FORMULA_VERSION,
        inputs=[
            {"name": "start_value", "value": start_value, "unit": "usd", "source_or_assumption_id": start_source_id},
            {"name": "end_value", "value": end_value, "unit": "usd", "source_or_assumption_id": end_source_id},
            {"name": "periods", "value": periods, "unit": "years", "source_or_assumption_id": "operator_or_default"},
        ],
        output_value=output_value,
        output_unit="ratio",
        computed_at=_now(),
        warnings=warnings,
    )


def calculate_margin(
    *, numerator: float, denominator: float, margin_name: str, numerator_source_id: str, denominator_source_id: str
) -> CalculationRecord:
    """A generic ratio margin (gross/operating/net/etc.) — numerator and
    denominator are whatever the caller says they are; this just divides and
    records where each side came from."""
    warnings: list[str] = []
    if denominator == 0:
        warnings.append(f"{margin_name} undefined — denominator is zero")
        output_value = 0.0
    else:
        output_value = numerator / denominator
    return CalculationRecord(
        calculation_id=_new_calculation_id(),
        formula_name=margin_name,
        formula_version=FORMULA_VERSION,
        inputs=[
            {"name": "numerator", "value": numerator, "unit": "usd", "source_or_assumption_id": numerator_source_id},
            {"name": "denominator", "value": denominator, "unit": "usd", "source_or_assumption_id": denominator_source_id},
        ],
        output_value=output_value,
        output_unit="ratio",
        computed_at=_now(),
        warnings=warnings,
    )


def calculate_benchmark_hurdle(
    *,
    subject_return: float,
    benchmark_return: float,
    subject_label: str,
    benchmark_label: str,
    subject_source_id: str,
    benchmark_source_id: str,
) -> CalculationRecord:
    """The excess return the subject would need over the benchmark — design
    doc §9's transparent hurdle, not a composite opportunity score. A
    positive output means the subject's own recent return already exceeds
    the benchmark's; it does NOT mean the investment case is good, only that
    this one input to the hurdle table favors the subject over the control."""
    return CalculationRecord(
        calculation_id=_new_calculation_id(),
        formula_name="benchmark_hurdle_gap",
        formula_version=FORMULA_VERSION,
        inputs=[
            {
                "name": f"{subject_label}_return",
                "value": subject_return,
                "unit": "ratio",
                "source_or_assumption_id": subject_source_id,
            },
            {
                "name": f"{benchmark_label}_return",
                "value": benchmark_return,
                "unit": "ratio",
                "source_or_assumption_id": benchmark_source_id,
            },
        ],
        output_value=subject_return - benchmark_return,
        output_unit="ratio",
        computed_at=_now(),
        warnings=[],
    )
