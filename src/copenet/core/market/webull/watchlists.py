"""Import the operator's real Webull watchlists into CopeNet's WatchlistStore.

This is a pull, not a subscription: every import re-reads Webull live, so edits made in the
Webull app show up the next time the operator imports. Empty Webull lists are skipped — the
account carries ~21 lists but only a dozen have instruments, and CopeNet caps at 20.

Uses the `webull.data` lane (`DataClient`), which needs no market-data subscription for
watchlist reads — verified live 2026-07-28, see docs/plans/WEBULL_API_SURFACE.md.
"""

from __future__ import annotations

import logging
from typing import Any

from ..watchlist_store import WatchlistStore

logger = logging.getLogger(__name__)

IMPORT_LIST_LIMIT = 20


def fetch_watchlists(data_client) -> list[dict[str, Any]]:
    """[{name, symbols: [{symbol, name}]}] for every non-empty Webull list, sort order preserved."""
    raw = data_client.watchlist.get_watchlist().json()
    lists: list[dict[str, Any]] = []
    for row in raw if isinstance(raw, list) else []:
        if not isinstance(row, dict) or not row.get("watchlist_id"):
            continue
        name = str(row.get("name") or "").strip()
        if not name:
            continue
        detail = data_client.watchlist.get_instruments(str(row["watchlist_id"])).json()
        instruments = detail.get("instruments") if isinstance(detail, dict) else None
        symbols = [
            {"symbol": str(item.get("symbol")).upper(), "name": str(item.get("name") or "")}
            for item in instruments or []
            if isinstance(item, dict) and item.get("symbol")
        ]
        if symbols:
            lists.append({"name": name, "symbols": symbols})
    logger.info("Webull watchlists: %d non-empty list(s)", len(lists))
    return lists


def import_into_store(store: WatchlistStore, lists: list[dict[str, Any]]) -> dict[str, Any]:
    """Replace-by-name upsert. Returns {imported: [{name, count}], skipped: [...]}."""
    imported: list[dict[str, Any]] = []
    skipped: list[str] = []
    for entry in lists[:IMPORT_LIST_LIMIT]:
        try:
            store.replace_list(entry["name"], entry["symbols"])
        except ValueError as exc:
            skipped.append(f"{entry['name']}: {exc}")
            continue
        imported.append({"name": entry["name"], "count": len(entry["symbols"])})
    skipped.extend(f"{entry['name']}: list limit reached" for entry in lists[IMPORT_LIST_LIMIT:])
    return {"imported": imported, "skipped": skipped}
