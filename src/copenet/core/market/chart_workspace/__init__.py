"""Shared chart domain used by the operator UI and scoped agent tools."""
from .models import MarketTurnContext
from .store import ChartStore


def get_chart_store(orchestrator) -> ChartStore:
    store = getattr(orchestrator, "_chart_store", None)
    if store is None:
        store = ChartStore(orchestrator._session_store.path.parent / "market" / "chart-workspace.sqlite3")
        orchestrator._chart_store = store
    return store


__all__ = ["ChartStore", "MarketTurnContext", "get_chart_store"]
