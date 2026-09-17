"""Model-facing FRED macro discovery, retrieval, and curated snapshot tools."""

from __future__ import annotations

import asyncio

from copenet.core.market.financials import default_market_dir
from copenet.core.market.fred import FredClient
from copenet.core.tools.contracts import (
    ToolDescriptor,
    ToolExecutionContext,
    ToolExecutionRequest,
    ToolExecutionResult,
)


def _client() -> FredClient:
    return FredClient(default_market_dir() / "fred")


async def get_macro_snapshot(request: ToolExecutionRequest, context: ToolExecutionContext) -> ToolExecutionResult:
    del context
    payload = await _client().snapshot(refresh=bool(request.arguments.get("refresh")))
    available = payload["seriesCount"] - payload["unavailableCount"]
    return ToolExecutionResult(
        tool_id=request.tool_id,
        ok=True,
        summary=f"FRED macro snapshot: {available}/{payload['seriesCount']} series available",
        output=payload,
    )


async def search_macro_series(request: ToolExecutionRequest, context: ToolExecutionContext) -> ToolExecutionResult:
    del context
    query = str(request.arguments.get("query") or "").strip()
    payload = await _client().search(
        query,
        limit=int(request.arguments.get("limit") or 10),
        refresh=bool(request.arguments.get("refresh")),
    )
    results = [_search_result(row) for row in payload.get("seriess") or []]
    output = {
        "query": query,
        "results": results,
        "resultCount": len(results),
        "cache": payload["cache"],
        "guidance": "Choose series by meaning, units, frequency, seasonal adjustment, and recency; then call market.macro.series.",
    }
    return ToolExecutionResult(
        tool_id=request.tool_id,
        ok=True,
        summary=f"Found {len(results)} FRED series for {query!r}",
        output=output,
    )


async def get_macro_series(request: ToolExecutionRequest, context: ToolExecutionContext) -> ToolExecutionResult:
    del context
    raw_ids = request.arguments.get("seriesIds")
    if not isinstance(raw_ids, list) or not raw_ids:
        raise ValueError("seriesIds must be a non-empty list")
    series_ids = list(dict.fromkeys(str(value).strip().upper() for value in raw_ids if str(value).strip()))[:8]
    client = _client()

    async def load(series_id: str) -> dict:
        try:
            payload = await client.series(
                series_id,
                limit=int(request.arguments.get("limit") or 120),
                observation_start=_optional(request.arguments.get("observationStart")),
                observation_end=_optional(request.arguments.get("observationEnd")),
                vintage_date=_optional(request.arguments.get("vintageDate")),
                refresh=bool(request.arguments.get("refresh")),
            )
            payload["plot"] = {
                "xField": "date",
                "yField": "value",
                "points": [
                    {"date": row["date"], "value": row["value"]}
                    for row in reversed(payload["observations"])
                    if row["value"] is not None
                ],
            }
            return {"seriesId": series_id, "ok": True, "data": payload}
        except Exception as exc:
            return {"seriesId": series_id, "ok": False, "error": str(exc)}

    results = await asyncio.gather(*(load(series_id) for series_id in series_ids))
    successful = sum(bool(result["ok"]) for result in results)
    return ToolExecutionResult(
        tool_id=request.tool_id,
        ok=True,
        summary=f"Retrieved {successful}/{len(results)} FRED series",
        output={
            "results": results,
            "requestedSeriesIds": series_ids,
            "vintageDate": _optional(request.arguments.get("vintageDate")),
            "guidance": "Observations are newest-first; plot.points are oldest-first. Compare series only after checking units, frequency, and dates.",
        },
    )


def _search_result(row: dict) -> dict:
    return {
        "seriesId": row.get("id"),
        "title": row.get("title"),
        "frequency": row.get("frequency"),
        "units": row.get("units"),
        "seasonalAdjustment": row.get("seasonal_adjustment"),
        "observationStart": row.get("observation_start"),
        "observationEnd": row.get("observation_end"),
        "sourceLastUpdatedAt": row.get("last_updated"),
        "popularity": row.get("popularity"),
        "notes": row.get("notes"),
    }


def _optional(value) -> str | None:
    text = str(value or "").strip()
    return text or None


DESCRIPTORS = [
    ToolDescriptor(
        id="market.macro.snapshot",
        name="Get Curated Macro Snapshot",
        description=(
            "Get one organized FRED snapshot covering growth, labor, inflation, rates, credit, liquidity, housing, and consumers. "
            "Each typed row includes its series id, transformation, units, observation date, source update time, cache age, next cache refresh, "
            "and a clearly labeled cadence-based estimate for the next observation."
        ),
        category="context",
        input_schema={
            "type": "object",
            "properties": {"refresh": {"type": "boolean", "description": "Bypass fresh cache entries; stale data still serves if FRED fails."}},
            "additionalProperties": False,
        },
        capabilities=["market-data", "fred"],
        evidence_role="grounding",
        side_effect="read",
    ),
    ToolDescriptor(
        id="market.macro.search",
        name="Search FRED Series",
        description=(
            "Explore FRED's full series catalog by plain-language topic before retrieving observations. "
            "Returns series ids plus titles, units, frequencies, seasonal adjustment, coverage dates, popularity, source update time, and notes."
        ),
        category="context",
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Economic concept or niche topic to find."},
                "limit": {"type": "integer", "minimum": 1, "maximum": 25, "description": "Maximum metadata matches; default 10."},
                "refresh": {"type": "boolean"},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
        capabilities=["market-data", "fred"],
        evidence_role="discovery",
        side_effect="read",
    ),
    ToolDescriptor(
        id="market.macro.series",
        name="Get FRED Series",
        description=(
            "Retrieve one to eight FRED series with metadata, typed nullable observations, cache freshness, source timestamps, and plot-ready points. "
            "Use vintageDate for point-in-time historical research that must avoid revised-data look-ahead bias."
        ),
        category="context",
        input_schema={
            "type": "object",
            "properties": {
                "seriesIds": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 8},
                "limit": {"type": "integer", "minimum": 2, "maximum": 5000, "description": "Observations per series; default 120."},
                "observationStart": {"type": "string", "description": "YYYY-MM-DD observation lower bound."},
                "observationEnd": {"type": "string", "description": "YYYY-MM-DD observation upper bound."},
                "vintageDate": {"type": "string", "description": "YYYY-MM-DD ALFRED knowledge date."},
                "refresh": {"type": "boolean"},
            },
            "required": ["seriesIds"],
            "additionalProperties": False,
        },
        capabilities=["market-data", "fred"],
        evidence_role="grounding",
        side_effect="read",
    ),
]

HANDLERS = {
    "market.macro.snapshot": get_macro_snapshot,
    "market.macro.search": search_macro_series,
    "market.macro.series": get_macro_series,
}
