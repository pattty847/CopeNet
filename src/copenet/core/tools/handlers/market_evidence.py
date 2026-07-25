"""Compact SEC and fundamentals evidence for model reasoning."""

from __future__ import annotations

import asyncio

from copenet.core.market.edgar import fetch_fundamentals, fetch_ticker_evidence
from copenet.core.tools.contracts import (
    ToolDescriptor,
    ToolExecutionContext,
    ToolExecutionRequest,
    ToolExecutionResult,
)

DEFAULT_DAYS_BACK = 90
DEFAULT_EVIDENCE_LIMIT = 24
MAX_EVIDENCE_LIMIT = 80


async def get_market_evidence(
    request: ToolExecutionRequest,
    context: ToolExecutionContext,
) -> ToolExecutionResult:
    del context
    symbol = str(request.arguments.get("symbol") or "").strip().upper()
    if not symbol:
        raise ValueError("symbol is required")
    days_back = max(30, min(int(request.arguments.get("daysBack") or DEFAULT_DAYS_BACK), 3650))
    evidence_limit = max(1, min(int(request.arguments.get("limit") or DEFAULT_EVIDENCE_LIMIT), MAX_EVIDENCE_LIMIT))
    refresh = bool(request.arguments.get("refresh"))
    include_fundamentals = request.arguments.get("includeFundamentals") is not False

    evidence_task = fetch_ticker_evidence(symbol, refresh=refresh, days_back=days_back)
    fundamentals_task = fetch_fundamentals(symbol) if include_fundamentals else _no_fundamentals()
    evidence_payload, fundamentals = await asyncio.gather(evidence_task, fundamentals_task)
    wire = evidence_payload.to_wire()
    evidence = wire.get("evidence")
    total_evidence = len(evidence) if isinstance(evidence, list) else 0
    wire["evidence"] = evidence[:evidence_limit] if isinstance(evidence, list) else []
    wire.pop("events", None)  # chart-marker duplicates add tokens but no model evidence
    wire.update(
        {
            "daysBack": days_back,
            "evidenceCount": total_evidence,
            "evidenceReturned": len(wire["evidence"]),
            "fundamentals": fundamentals,
        }
    )

    insider_net = wire.get("insiderNet")
    net_label = "no classified Form 4 window"
    if isinstance(insider_net, dict):
        window = insider_net.get(f"d{days_back}") or insider_net.get("d90") or insider_net.get("d30")
        if isinstance(window, dict):
            net_label = f"{window.get('buys', 0)} buys / {window.get('sells', 0)} sells"
    summary = f"{symbol} SEC evidence: {total_evidence} items; {net_label}"
    return ToolExecutionResult(tool_id=request.tool_id, ok=True, summary=summary, output=wire)


async def _no_fundamentals() -> None:
    return None


DESCRIPTORS = [
    ToolDescriptor(
        id="market.evidence",
        name="Get Market Evidence",
        description=(
            "Get a compact, source-linked evidence packet for one public-company ticker. Returns "
            "classified SEC Form 4 transactions (open-market buys/sells kept distinct from gifts, "
            "tax withholding, option exercise, and conversion), Form 144 planned-sale intent, material "
            "8-K activity, trailing insider net windows, and recent XBRL revenue/EPS fundamentals. "
            "Use this when evaluating insider activity, SEC filings, or whether price action has "
            "fundamental/filing support. This is evidence, not investment advice. Cached data is used "
            "unless `refresh` is explicitly requested."
        ),
        category="context",
        input_schema={
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Public-company ticker, e.g. 'AAPL'."},
                "daysBack": {
                    "type": "integer",
                    "minimum": 30,
                    "maximum": 3650,
                    "description": f"SEC history window in days. Default {DEFAULT_DAYS_BACK}.",
                },
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": MAX_EVIDENCE_LIMIT,
                    "description": f"Maximum source-linked evidence rows returned. Default {DEFAULT_EVIDENCE_LIMIT}.",
                },
                "includeFundamentals": {
                    "type": "boolean",
                    "description": "Include recent SEC XBRL revenue and EPS series. Default true.",
                },
                "refresh": {
                    "type": "boolean",
                    "description": "Refresh CopeTech-Edgar caches before reading. Default false.",
                },
            },
            "required": ["symbol"],
            "additionalProperties": False,
        },
        capabilities=["market-data", "sec-filings"],
        evidence_role="grounding",
        side_effect="read",
    )
]

HANDLERS = {"market.evidence": get_market_evidence}
