"""Two-decimal numeric CSV for model input; stored resources keep their typed rows."""
from __future__ import annotations

import csv
from datetime import datetime, timezone
import io
import json
import math

FLOAT_DECIMALS = 2
SMALL_FLOAT_SIGNIFICANT_DIGITS = 4


def compact_json(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def round_float(value: float) -> float:
    """Two decimals everywhere the model reads a float.

    A value that would round to zero but is not zero (sub-penny prices, tiny
    rates) keeps four significant digits instead: 0.0043 must not become 0.0.
    """
    if not math.isfinite(value):
        return value
    rounded = round(value, FLOAT_DECIMALS)
    if rounded == 0 and value != 0:
        return float(f"{value:.{SMALL_FLOAT_SIGNIFICANT_DIGITS}g}")
    return rounded


def round_floats(value):
    """Apply `round_float` through nested dicts and lists; every other value is untouched."""
    if type(value) is float:
        return round_float(value)
    if isinstance(value, dict):
        return {key: round_floats(item) for key, item in value.items()}
    if isinstance(value, list):
        return [round_floats(item) for item in value]
    return value


def _cell(value) -> str:
    if type(value) is float:
        return compact_json(round_float(value))
    return compact_json(value)


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
    writer.writerows([_cell(row[key]) if key in row else "" for key in columns] for row in rows)
    return stream.getvalue().rstrip("\n")


def _utc(value: int | float) -> str:
    try:
        return datetime.fromtimestamp(value, timezone.utc).isoformat().replace("+00:00", "Z")
    except (ValueError, OverflowError, OSError):
        return f"unrepresentable UTC date ({value})"


_FLOAT_RULE = (f"Floats are rounded to {FLOAT_DECIMALS} decimals (values under 0.01 keep "
               f"{SMALL_FLOAT_SIGNIFICANT_DIGITS} significant digits)")
LEGEND = _FLOAT_RULE + "; null = recorded gap, empty cell = absent field."
JSON_LEGEND = _FLOAT_RULE + "."
CANDLE_LEGEND = (" t=timestamp; o,h,l,c=open,high,low,close; v=volume; any other column is an indicator output"
                 " named in metadata.columns. Units and time basis are in metadata; unspecified units are unknown.")


def trim_read_metadata(metadata: dict, timeframe: str | None) -> dict:
    """Drop provenance the model already holds from the turn packet.

    Every candle read used to repeat the split list and completion status for
    every timeframe — 369 tokens, about a fifth of a 40-row read. The fingerprint
    still names the splits, and only the requested timeframe's completion matters.
    """
    provenance = metadata.get("priceProvenance")
    if not isinstance(provenance, dict):
        return metadata
    trimmed = {key: value for key, value in provenance.items() if key != "splits"}
    completion = trimmed.get("timeframeCompletion")
    if isinstance(completion, dict) and timeframe in completion:
        trimmed["timeframeCompletion"] = {timeframe: completion[timeframe]}
    return {**metadata, "priceProvenance": trimmed}


def format_resource(resource: dict) -> str:
    rows = resource["rows"]
    header = {key: value for key, value in resource.items() if key != "rows"}
    times = [row["t"] for row in rows if type(row.get("t")) in (int, float)]
    if times:
        header["returnedRange"] = {"from": min(times), "to": max(times)}
        if resource.get("metadata", {}).get("timestampUnit") == "seconds":
            header["returnedRange"]["utc"] = [_utc(min(times)), _utc(max(times))]
    table = numeric_csv(rows)
    description = compact_json(round_floats(header))
    if table is None:
        # The fallback carries the resources a CSV cannot hold, and those are the ones with
        # the most floats: the ticker overview's quote and stats, evidence rows, drawing
        # anchors, an account position. Rounding only the header left all of them at full
        # precision, so the path meant for structure was shipping 17-digit prices.
        return description + "\n" + JSON_LEGEND + "\nJSON rows:\n" + compact_json(round_floats(rows))
    legend = LEGEND + (CANDLE_LEGEND if resource.get("kind") == "candles" else "")
    return description + "\n" + legend + "\n```csv\n" + table + "\n```"


def format_context(payload: dict) -> str:
    header = {key: value for key, value in payload.items() if key != "samples"}
    return "\n\n".join([compact_json(round_floats(header)), *(format_resource(sample) for sample in payload["samples"])])


def format_read(payload: dict, *, max_chars: int) -> str:
    """Fit whole rows and preserve the continuation offset, including narrow budgets."""
    count = len(payload["rows"])
    metadata = payload.get("metadata")
    if isinstance(metadata, dict):
        payload = {**payload, "metadata": trim_read_metadata(metadata, metadata.get("timeframe"))}

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
