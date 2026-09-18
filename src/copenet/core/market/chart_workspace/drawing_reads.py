"""The drawings table in the chart packet: one row per painted drawing, with its reading guide.

The browser computes each row from the anchors, bars and scale it painted with
(`drawings/reads.ts`), so the model reads the chart the operator is looking at. This module
only joins edit authority from the document, fits the table to a budget, and writes the CSV.
"""
from __future__ import annotations

import csv
import io

from .model_tables import _cell


def _text_or_number(value) -> str:
    # Strings go in bare: JSON-quoting them inside CSV triples every quote mark.
    return value if isinstance(value, str) else _cell(value)

RESOURCE_KEY = "chart:drawing-reads"
ROWS_IN_PACKET = 40
COLUMNS = ("n", "kind", "owner", "id", "color", "label", "t1", "p1", "t2", "p2", "t3", "p3",
           "extends", "perBar", "perBarPct", "atLast", "vsClosePct", "detail")

GUIDE = (
    "One row per drawing painted on this chart and timeframe when this turn was captured; drawings "
    "you create during the turn appear in market.chart.document, not here. owner=you is the operator's own "
    "drawing: read-only, and the levels the operator is watching. n numbers the rows so you can "
    "refer to one; id is present only on this session's agent drawings, the ones you may edit. color is how the operator will refer to it. t1..t3 are anchor "
    "timestamps that join the candle table's t column; p1..p3 are anchor prices (a position is "
    "p1=entry, p2=target, p3=stop; a zone is its two price bounds). extends says where the stroke "
    "runs: none stops at t2, right continues past t2, both runs across the chart. Lines are "
    "measured in candles, never calendar days. atLast is the line's value at the latest candle "
    "(for extends=none past its end it is the extrapolation, not a drawn line). To project N "
    "candles ahead: atLast + perBar*N on a linear axis; atLast*(1+perBarPct/100)^N when the column "
    "is perBarPct (logarithmic axis). vsClosePct is the latest close relative to atLast, or to the "
    "nearest bound of a zone (0 = inside). detail holds kind-specific facts: fib ratio=price pairs "
    "(ratio 0 is p1), measurement size, position R:R, a channel's parallel rail, or the candle-table "
    "column that carries an anchored VWAP's full series. Empty cell = not applicable."
)


def drawing_table(rows: list[dict], objects: list[dict], session_key: str | None) -> dict | None:
    """Rows joined with edit authority. None when nothing is painted."""
    if not rows:
        return None
    owners = {item.get("id"): item.get("owner") or {} for item in objects}
    joined = []
    for number, row in enumerate(rows[:ROWS_IN_PACKET], start=1):
        owner = owners.get(row.get("id"), {})
        editable = owner.get("kind") == "agent" and owner.get("sessionKey") == session_key
        # A UUID costs about twenty tokens. Only a drawing the model may edit needs one.
        joined.append({**row, "n": number, "id": row.get("id") if editable else None})
    return {"painted": len(rows), "listed": len(joined), "rows": joined}


def format_drawing_table(table: dict) -> str:
    rows = table["rows"]
    columns = [name for name in COLUMNS if any(row.get(name) not in (None, "") for row in rows)]
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(columns)
    writer.writerows([_text_or_number(row[name]) if row.get(name) not in (None, "") else "" for name in columns] for row in rows)
    return "Drawings. " + GUIDE + "\n```csv\n" + stream.getvalue().rstrip("\n") + "\n```"
