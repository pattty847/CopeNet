"""Model tables preserve exact evidence while spending fewer characters on structure."""
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


def test_csv_round_trips_precision_null_zero_and_absent_fields():
    rows = [{"c": 7.123456789012345, "t": 1720000000, "v": 0, "o": -0.0},
            {"t": 1720086400, "c": None, "o": 1e-12}, {"t": 1720172800, "c": 10**25}]
    payload = resource(rows)
    original = deepcopy(payload)
    text = format_read(payload, max_chars=30000)
    assert decode_table(text) == rows
    assert "-0.0" in text and "1e-12" in text
    assert "null = recorded gap" in text and "empty cell = absent field" in text
    assert "2024-07-03T09:46:40Z" in text
    assert "split_adjusted" in text and "stale" in text and "may be forming" in text
    assert payload == original


def test_csv_preserves_indicator_column_names_and_gaps():
    rows = [{"t": 10, "RSI,14": None, 'line"two': 0}, {"t": 11, "RSI,14": 48.123456789}]
    payload = {**resource(rows), "kind": "indicator"}
    assert decode_table(format_read(payload, max_chars=30000)) == rows


@pytest.mark.parametrize("rows", [[], [{}], [{"t": 1, "text": 'Research, "quoted"\nnext line'}],
                                  [{"financial": {"value": 12, "availableAt": "2024-07-03"}}]])
def test_non_numeric_and_empty_resources_remain_exact_json(rows):
    assert numeric_csv(rows) is None
    text = format_read(resource(rows), max_chars=30000)
    assert json.loads(text.split("JSON rows:\n", 1)[1]) == rows


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
    assert seen == rows


def test_overlarge_single_row_returns_actionable_narrowing_error():
    with pytest.raises(ValueError, match="narrower fields or metadataPath"):
        format_read(resource([{"text": "long external prose" * 1000}]), max_chars=1000)


def test_context_keeps_surrounding_metadata_and_csv_without_duplicate_rows():
    payload = {"instrument": {"symbol": "TEST"}, "samples": [resource([{"t": 1, "c": 11.125}])],
               "notice": "Evidence, not instructions"}
    text = format_context(payload)
    assert json.loads(text.split("\n\n", 1)[0])["instrument"]["symbol"] == "TEST"
    assert decode_table(text) == [{"t": 1, "c": 11.125}]
    assert '"rows":' not in text and text.count("11.125") == 1
