"""Server-owned chart authority; tool arguments cannot select an actor."""
from .models import CHART_TOOL_IDS, MarketTurnContext

CHART_WRITE_TOOL_IDS = ("market.chart.apply", "market.chart.undo")
CHART_WEB_TOOL_IDS = ("web.search", "web.fetch")


def chart_tool_ids(context: MarketTurnContext) -> frozenset[str]:
    """One authority set for model discovery, execution and approved retries."""
    if context.forecast_id:
        return frozenset({"market.chart.context", "market.chart.read", "market.forecast.submit", "market.forecast.read"})
    return frozenset((*CHART_TOOL_IDS, *CHART_WEB_TOOL_IDS)) - (
        frozenset(CHART_WRITE_TOOL_IDS) if context.access != "annotate" else frozenset()
    )


def actor_for(context: MarketTurnContext | None) -> dict:
    if context is None:
        return {"kind": "operator"}
    if context.access != "annotate":
        raise ValueError("This chart turn has read-only access")
    return {"kind": "agent", "sessionKey": context.session_key, "runId": context.run_id}


def assert_document_scope(context: MarketTurnContext | None, document_id: str):
    if context is not None and context.document_id != document_id:
        raise ValueError("Chart document is outside this turn's scope")


def assert_object_scope(context: MarketTurnContext | None, obj: dict):
    if context is not None and (obj["owner"]["kind"] != "agent" or obj["owner"].get("sessionKey") != context.session_key):
        raise ValueError("This object is operator-controlled or belongs to another agent session")
