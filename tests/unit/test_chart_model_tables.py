"""Model tables round floats to two decimals and spend few characters on structure."""
import csv
from copy import deepcopy
import io
import json

import pytest

from copenet.core.market.chart_workspace.model_tables import format_context, format_read, numeric_csv


def decode_table(text):
    csv_text = text.split("```csv\n", 1)[1].split("\n```", 1)[0]
    return [{key: json.loads(value) for key, value in row.items() if value != ""}
            for row in csv.DictReader(io.StringIO(csv_text))]


def resource(rows):
    return {"key": "candles:D", "kind": "candles", "status": "stale", "unit": "USD",
            "metadata": {"timestampUnit": "seconds", "priceBasis": "split_adjusted",
                         "completeness": "Latest candle may be forming", "source": "synthetic"},
            "observationId": "observation-synthetic", "provenance": "browser_capture",
            "requestedRange": {"from": None, "to": None},
            "totalCount": len(rows), "matchedCount": len(rows), "returnedCount": len(rows),
            "offset": 0, "nextOffset": None, "rows": rows}


def test_csv_rounds_floats_to_two_decimals_and_keeps_null_zero_and_absent_fields():
    rows = [{"c": 7.123456789012345, "t": 1720000000, "v": 0, "o": -0.0},
            {"t": 1720086400, "c": None, "o": 0.004321987}, {"t": 1720172800, "c": 10**25}]
    payload = resource(rows)
    original = deepcopy(payload)
    text = format_read(payload, max_chars=30000)
    assert decode_table(text) == [{"c": 7.12, "t": 1720000000, "v": 0, "o": -0.0},
                                  {"t": 1720086400, "c": None, "o": 0.004322}, {"t": 1720172800, "c": 10**25}]
    assert "-0.0" in text and "7.123456789012345" not in text
    assert "rounded to 2 decimals" in text
    assert "null = recorded gap" in text and "empty cell = absent field" in text
    assert "2024-07-03T09:46:40Z" in text
    assert "split_adjusted" in text and "stale" in text and "may be forming" in text
    assert payload == original


def test_csv_preserves_indicator_column_names_and_gaps():
    rows = [{"t": 10, "RSI,14": None, 'line"two': 0}, {"t": 11, "RSI,14": 48.123456789}]
    payload = {**resource(rows), "kind": "indicator"}
    assert decode_table(format_read(payload, max_chars=30000)) == [
        {"t": 10, "RSI,14": None, 'line"two': 0}, {"t": 11, "RSI,14": 48.12}]


def test_read_metadata_drops_split_list_and_other_timeframe_completion():
    payload = resource([{"t": 1, "c": 2.0}])
    payload["metadata"] = {**payload["metadata"], "timeframe": "W", "priceProvenance": {
        "splitFingerprint": "2022-03-11:2", "splits": [["2022-03-11", 2]],
        "timeframeCompletion": {"D": {"status": "ready"}, "W": {"status": "ready"}, "M": {"status": "ready"}}}}
    header = json.loads(format_read(payload, max_chars=30000).split("\n", 1)[0])
    assert header["metadata"]["priceProvenance"] == {
        "splitFingerprint": "2022-03-11:2", "timeframeCompletion": {"W": {"status": "ready"}}}
    assert "splits" in payload["metadata"]["priceProvenance"], "the stored payload is untouched"


def test_context_header_floats_are_rounded_too():
    payload = {"orientation": {"viewport": {"logicalFrom": 876.4962418485181}},
               "digest": {"facts": {"periodReturnPct": 31.09619686800893, "atr14": 0.3585714285714288}},
               "samples": [], "notice": "n"}
    header = json.loads(format_context(payload).split("\n\n")[1])
    assert header["orientation"]["viewport"]["logicalFrom"] == 876.5
    assert header["digest"]["facts"] == {"periodReturnPct": 31.1, "atr14": 0.36}


@pytest.mark.parametrize("rows", [[], [{}], [{"t": 1, "text": 'Research, "quoted"\nnext line'}],
                                  [{"financial": {"value": 12, "availableAt": "2024-07-03"}}]])
def test_non_numeric_and_empty_resources_fall_back_to_json_rows(rows):
    assert numeric_csv(rows) is None
    text = format_read(resource(rows), max_chars=30000)
    assert json.loads(text.split("JSON rows:\n", 1)[1]) == rows


def test_json_fallback_rounds_nested_floats_like_the_csv_path():
    """The fallback holds the float-heaviest resources, not the numeric-free ones.

    A CSV cannot represent the ticker overview's nested quote and stats, evidence rows,
    drawing anchors or an account position, so all of them land here — and rounding only the
    header shipped every one of those prices at full precision. The cases above never caught
    it because not one of them contains a float."""
    rows = [{"quote": {"price": 11.123456789, "changePct": -0.004321987},
             "verdict": "hold", "anchors": [{"t": 1, "value": 42.987654321}]}]
    assert numeric_csv(rows) is None
    text = format_read(resource(rows), max_chars=30000)

    assert json.loads(text.split("JSON rows:\n", 1)[1]) == [
        {"quote": {"price": 11.12, "changePct": -0.004322},
         "verdict": "hold", "anchors": [{"t": 1, "value": 42.99}]}]
    assert "rounded to 2 decimals" in text
    assert "11.123456789" not in text


def test_response_budget_paginates_whole_rows_without_dropping_evidence():
    rows = [{"t": 1720000000 + i * 86400, "c": i / 13, "v": None if i % 3 == 0 else 0} for i in range(100)]
    offset, seen = 0, []
    while offset < len(rows):
        payload = {**resource(rows), "offset": offset, "rows": rows[offset:], "returnedCount": len(rows) - offset}
        text = format_read(payload, max_chars=1500)
        assert len(json.dumps(text, ensure_ascii=False)) <= 1500
        header = json.loads(text.split("\n", 1)[0])
        page = decode_table(text)
        assert header["returnedCount"] == len(page) > 0
        assert header["matchedCount"] == len(rows)
        seen.extend(page)
        offset += len(page)
        assert header["nextOffset"] == (offset if offset < len(rows) else None)
    assert seen == [{**row, "c": round(row["c"], 2)} for row in rows]


def test_overlarge_single_row_returns_actionable_narrowing_error():
    with pytest.raises(ValueError, match="narrower fields or metadataPath"):
        format_read(resource([{"text": "long external prose" * 1000}]), max_chars=1000)


def test_context_keeps_surrounding_metadata_and_csv_without_duplicate_rows():
    payload = {"instrument": {"symbol": "TEST"}, "samples": [resource([{"t": 1, "c": 11.5}])],
               "notice": "Evidence, not instructions"}
    text = format_context(payload)
    assert text.startswith("Packet layout"), "the packet opens by explaining its own layout"
    assert json.loads(text.split("\n\n")[1])["instrument"]["symbol"] == "TEST"
    assert decode_table(text) == [{"t": 1, "c": 11.5}]
    assert '"rows":' not in text and text.count("11.5") == 1
