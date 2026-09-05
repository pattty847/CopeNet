"""Lossless numeric CSV for model input; stored resources keep their typed rows."""
from __future__ import annotations

import csv
from datetime import datetime, timezone
import io
import json


def compact_json(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def numeric_csv(rows: list[dict]) -> str | None:
    """Empty CSV cells mean absent fields; the literal null means a recorded gap."""
    if not rows or not all(value is None or type(value) in (int, float, bool)
                           for row in rows for value in row.values()):
        return None
    fields = list(dict.fromkeys(key for row in rows for key in row))
    if not fields:
        return None
    columns = [key for key in ("t", "o", "h", "l", "c", "v") if key in fields]
    columns += [key for key in fields if key not in columns]
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(columns)
    writer.writerows([compact_json(row[key]) if key in row else "" for key in columns] for row in rows)
    return stream.getvalue().rstrip("\n")


def _utc(value: int | float) -> str:
    try:
        return datetime.fromtimestamp(value, timezone.utc).isoformat().replace("+00:00", "Z")
    except (ValueError, OverflowError, OSError):
        return f"unrepresentable UTC date ({value})"


def format_resource(resource: dict) -> str:
    rows = resource["rows"]
    header = {key: value for key, value in resource.items() if key != "rows"}
    times = [row["t"] for row in rows if type(row.get("t")) in (int, float)]
    if times:
        header["returnedRange"] = {"from": min(times), "to": max(times)}
        if resource.get("metadata", {}).get("timestampUnit") == "seconds":
            header["returnedRange"]["utc"] = [_utc(min(times)), _utc(max(times))]
    table = numeric_csv(rows)
    description = compact_json(header)
    if table is None:
        return description + "\nJSON rows:\n" + compact_json(rows)
    legend = "CSV values are exact; null = recorded gap, empty cell = absent field."
    if resource.get("kind") == "candles":
        legend += " t=timestamp; o,h,l,c=open,high,low,close; v=volume. Units and time basis are in metadata; unspecified units are unknown."
    return description + "\n" + legend + "\n```csv\n" + table + "\n```"


def format_context(payload: dict) -> str:
    header = {key: value for key, value in payload.items() if key != "samples"}
    return "\n\n".join([compact_json(header), *(format_resource(sample) for sample in payload["samples"])])


def format_read(payload: dict, *, max_chars: int) -> str:
    """Fit whole rows and preserve the continuation offset, including narrow budgets."""
    count = len(payload["rows"])

    def render(size):
        end = payload["offset"] + size
        page = {**payload, "rows": payload["rows"][:size], "returnedCount": size,
                "nextOffset": end if end < payload["matchedCount"] else None}
        if size < count:
            page["modelOmissions"] = "Response budget; continue with nextOffset for remaining exact rows."
        return format_resource(page)

    text = render(count)
    # Count JSON string escaping too: tool loops place this text inside their envelope.
    if len(json.dumps(text, ensure_ascii=False)) <= max_chars:
        return text
    low, high = 0, count
    while low < high:
        middle = (low + high + 1) // 2
        if len(json.dumps(render(middle), ensure_ascii=False)) <= max_chars:
            low = middle
        else:
            high = middle - 1
    if not low:
        raise ValueError("One chart row or its metadata exceeds the model response budget; request narrower fields or metadataPath")
    return render(low)
