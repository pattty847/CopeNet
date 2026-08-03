"""Canonical SEC financial-series tool for model reasoning."""

from __future__ import annotations

from copenet.core.market.financials import (
    get_financial_series,
    supported_financial_metrics,
)
from copenet.core.tools.contracts import (
    ToolDescriptor,
    ToolExecutionContext,
    ToolExecutionRequest,
    ToolExecutionResult,
)


async def get_market_financials(
    request: ToolExecutionRequest,
    context: ToolExecutionContext,
) -> ToolExecutionResult:
    del context
    symbol = str(request.arguments.get("symbol") or "").strip().upper()
    if not symbol:
        raise ValueError("symbol is required")
    payload = await get_financial_series(
        symbol=symbol,
        metric=str(request.arguments.get("metric") or "revenue"),
        frequency=str(request.arguments.get("frequency") or "quarterly"),
        basis=str(request.arguments.get("basis") or "canonical"),
        alignment=str(request.arguments.get("alignment") or "availability"),
        as_of=_optional_string(request.arguments.get("asOf")),
        start=_optional_string(request.arguments.get("start")),
        end=_optional_string(request.arguments.get("end")),
        refresh=bool(request.arguments.get("refresh")),
        include_provenance=request.arguments.get("includeProvenance") is not False,
    )
    if payload is None:
        return ToolExecutionResult(
            tool_id=request.tool_id,
            ok=True,
            summary=f"No canonical financial series is available for {symbol}",
            output={"symbol": symbol, "observations": [], "warnings": ["unavailable"]},
        )
    observations = payload.get("observations") or []
    summary = (
        f"{symbol} {payload['frequency']} {payload['metric']}: "
        f"{len(observations)} point-in-time observations"
    )
    return ToolExecutionResult(
        tool_id=request.tool_id,
        ok=True,
        summary=summary,
        output=payload,
    )


def _optional_string(value) -> str | None:
    text = str(value or "").strip()
    return text or None


def _metric_ids() -> list[str]:
    ids = [str(entry.get("id")) for entry in supported_financial_metrics()]
    # The registry is empty only when copetech-edgar is not importable; keep the
    # schema valid so tool listing never breaks in that degraded state.
    return ids or ["revenue"]


DESCRIPTORS = [
    ToolDescriptor(
        id="market.financials",
        name="Get Canonical Financial Series",
        description=(
            "Get a normalized SEC financial series without reasoning about XBRL tags. "
            "Observations distinguish reporting period from the filing availability date "
            "and include units, derivations, provenance, confidence, and quality warnings. "
            "Use alignment='availability' and an asOf date for point-in-time-safe analysis."
        ),
        category="context",
        input_schema={
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Public-company ticker."},
                "metric": {
                    "type": "string",
                    "enum": _metric_ids(),
                    "description": (
                        "Canonical metric id: base SEC series (revenue, "
                        "operating_income, ...), derived composites (gross_margin, "
                        "fcf, ...), or price-backed valuation (trailing_pe)."
                    ),
                },
                "frequency": {
                    "type": "string",
                    "enum": ["quarterly", "annual", "ttm"],
                },
                "basis": {
                    "type": "string",
                    "enum": ["reported", "canonical"],
                    "description": "Canonical includes explicitly derived Q4 observations.",
                },
                "alignment": {
                    "type": "string",
                    "enum": ["availability", "period_end"],
                },
                "asOf": {"type": "string", "description": "YYYY-MM-DD knowledge cutoff."},
                "start": {"type": "string", "description": "YYYY-MM-DD period-end lower bound."},
                "end": {"type": "string", "description": "YYYY-MM-DD period-end upper bound."},
                "includeProvenance": {"type": "boolean"},
                "refresh": {"type": "boolean"},
            },
            "required": ["symbol"],
            "additionalProperties": False,
        },
        capabilities=["market-data", "sec-filings"],
        evidence_role="grounding",
        side_effect="read",
    )
]

HANDLERS = {"market.financials": get_market_financials}
