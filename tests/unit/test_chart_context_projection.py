"""Whole-viewport chart context stays useful and honest under tight budgets."""
from __future__ import annotations

from copenet.core.market.chart_workspace import ChartStore
from copenet.core.market.chart_workspace.requests import ReadRequest

INSTRUMENT = {
    "instrumentId": "test:SYN", "symbol": "SYN", "assetClass": "equity",
    "source": "synthetic", "currency": "USD",
}


def _scene(tmp_path, *, count: int = 800, extra_resources=()):
    store = ChartStore(tmp_path / "chart.sqlite3")
    document = store.workspace("primary", INSTRUMENT)["document"]
    start = 1_700_000_000
    rows = []
    for index in range(count):
        close = 100 + index / 20
        if index == 120:
            close = 240
        if index == 510:
            close = 45
        rows.append({
            "t": start + index * 86_400,
            "o": close - 1, "h": close + 2, "l": close - 2, "c": close,
            "v": 1_000 + index,
        })
    completion = {
        "status": "ready", "completedThrough": rows[-2]["t"],
        "completedCloseAt": "2026-01-01T21:00:00Z", "error": None,
    }
    indicator_rows = [{"t": row["t"], "mama": row["c"] - 2, "fama": row["c"] - 4} for row in rows]
    capture = {
        "schemaVersion": 1, "viewId": "view", "viewRevision": 1, "instrument": INSTRUMENT,
        "timeframe": "D", "range": "5Y", "viewport": {"from": rows[0]["t"], "to": rows[-1]["t"]},
        "selection": None, "settings": {"includeAccountContext": False, "logScale": False},
        "resources": [
            {"key": "candles:D", "kind": "candles", "label": "Synthetic daily", "unit": "USD",
             "status": "loaded", "rows": rows, "metadata": {"timeframe": "D", "timestampUnit": "seconds",
                                                                  "priceBasis": "split_adjusted", "completion": completion}},
            {"key": "indicator:mama", "kind": "indicator", "label": "MAMA / FAMA", "unit": "USD",
             "status": "loaded", "rows": indicator_rows,
             "metadata": {"timeframe": "D", "timestampUnit": "seconds", "visible": True}},
            {"key": "quote:displayed", "kind": "quote", "label": "Displayed quote", "status": "loaded",
             "rows": [{"price": rows[-1]["c"], "quoteTime": rows[-1]["t"]}],
             "metadata": {"source": "synthetic"}},
            *[resource(rows) if callable(resource) else resource for resource in extra_resources],
        ],
        "documentId": document["documentId"], "documentRevision": 0,
    }
    observation = store.capture("session", "capture", capture)
    context = store.resolve_context("session", "run", {
        "observationId": observation["observationId"], "documentId": document["documentId"],
        "viewId": "view", "detail": "balanced", "access": "read",
    })
    return store, context, rows


def test_digest_uses_every_completed_visible_bar_and_separates_forming_bar(tmp_path):
    store, context, rows = _scene(tmp_path)

    payload = store.context_payload(context, token_limit=5_000)
    digest = payload["digest"]

    assert digest["visibleBarCount"] == 800
    assert digest["completedBarCount"] == 799
    assert digest["unconfirmedBarCount"] == 1
    assert digest["latestCompletedBar"]["t"] == rows[-2]["t"]
    assert digest["latestCapturedBar"]["t"] == rows[-1]["t"]
    assert digest["facts"]["highestHigh"]["t"] == rows[120]["t"]
    assert digest["facts"]["lowestLow"]["t"] == rows[510]["t"]
    assert digest["facts"]["maxCloseDrawdownPct"]["peakT"] == rows[120]["t"]
    assert digest["facts"]["maxCloseDrawdownPct"]["troughT"] == rows[510]["t"]


def test_tight_budget_reports_adaptive_delivery_without_starving_latest_state(tmp_path):
    store, context, rows = _scene(tmp_path)

    payload = store.context_payload(context, token_limit=5_000)
    candle_coverage = next(item for item in payload["coverage"] if item["key"] == "candles:D")
    candle_sample = next(item for item in payload["samples"] if item["key"] == "candles:D")

    assert payload["estimatedTokens"] <= 5_000
    assert payload["latest"]["displayedQuote"]["price"] == rows[-1]["c"]
    assert payload["latest"]["indicators"][0]["latest"]["t"] == rows[-2]["t"]
    assert candle_coverage["delivery"] == "adaptive-viewport-v1"
    assert candle_coverage["deliveredCount"] < candle_coverage["focusMatchedCount"]
    assert candle_coverage["contiguousRanges"]
    assert any(item["key"] == "candles:D" and item["matched"] == 800 for item in payload["sampleOmissions"])
    delivered_times = {row["t"] for row in candle_sample["rows"]}
    assert rows[0]["t"] in delivered_times and rows[-1]["t"] in delivered_times
    assert rows[120]["t"] in delivered_times and rows[510]["t"] in delivered_times


def test_iso_time_bounds_normalize_to_canonical_epoch_seconds():
    request = ReadRequest.model_validate({
        "resourceKey": "candles:D",
        "from": "2026-01-02T00:00:00Z",
        "to": "2026-01-03T00:00:00+00:00",
    })

    assert request.from_ == 1_767_312_000
    assert request.to == 1_767_398_400


def test_iso_time_bounds_require_a_timezone():
    try:
        ReadRequest.model_validate({"resourceKey": "candles:D", "from": "2026-01-02"})
    except ValueError as exc:
        assert "timezone" in str(exc)
    else:
        raise AssertionError("timezone-free chart bound was accepted")


def test_packet_delivers_one_matrix_with_indicator_columns_on_candle_rows(tmp_path):
    store, context, rows = _scene(tmp_path, count=40)

    payload = store.context_payload(context)
    samples = {sample["key"]: sample for sample in payload["samples"]}

    assert set(samples) == {"quote:displayed", "candles:D"}, "indicators ride the candle table, not their own"
    matrix = samples["candles:D"]
    assert matrix["rows"][5] == {**rows[5], "mama": rows[5]["c"] - 2, "fama": rows[5]["c"] - 4}
    assert matrix["metadata"]["columns"] == {
        "mama": {"resource": "indicator:mama", "field": "mama"},
        "fama": {"resource": "indicator:mama", "field": "fama"},
    }
    indicator_coverage = next(item for item in payload["coverage"] if item["key"] == "indicator:mama")
    assert indicator_coverage["alignedTo"] == "candles:D"
    assert indicator_coverage["delivery"] == "exhaustive" and indicator_coverage["deliveredCount"] == 40


def test_packet_token_estimate_is_the_tokenizer_count_of_what_the_model_reads(tmp_path):
    from copenet.core.harness.token_count import count_text_tokens
    from copenet.core.market.chart_workspace.model_tables import format_context
    store, context, _ = _scene(tmp_path, count=40)

    payload = store.context_payload(context)

    assert payload["estimatedTokens"] == count_text_tokens(format_context(payload))


def test_context_tool_never_repeats_delivered_rows(tmp_path):
    store, context, _ = _scene(tmp_path, count=40)

    payload = store.context_payload(context, include_samples=False)

    assert payload["samples"] == [] and payload["coverage"] == []
    assert "never repeated" in payload["samplesNote"]
    assert payload["drawings"]["count"] == 0 and payload["drawings"]["readTool"] == "market.chart.document"
    assert payload["drawingTable"] is None
    assert payload["digest"]["visibleBarCount"] == 40


def _drawing_reads(rows):
    return {"key": "chart:drawing-reads", "kind": "drawing_reads", "label": "Drawings as painted", "status": "loaded",
            "rows": [
                {"id": "d1", "kind": "ray", "owner": "you", "color": "red", "label": "", "t1": rows[0]["t"], "p1": 100.0,
                 "t2": rows[20]["t"], "p2": 101.0, "extends": "right", "perBar": 0.05, "atLast": 101.95, "vsClosePct": -0.0049},
                {"id": "d2", "kind": "avwap", "owner": "you", "color": "purple", "label": "Earnings", "t1": rows[10]["t"],
                 "p1": 100.5, "extends": "right", "atLast": 101.123456, "vsClosePct": 0.8, "detail": "series in table column avwap"},
            ],
            "metadata": {"timeframe": "D", "logScale": False, "timestampUnit": "seconds"}}


def _avwap_column(rows):
    return {"key": "indicator:avwap", "kind": "indicator", "label": "Anchored VWAP (Earnings)", "status": "loaded",
            "rows": [{"t": row["t"], "value": None if index < 10 else row["c"] - 0.5} for index, row in enumerate(rows)],
            "metadata": {"timeframe": "D", "timestampUnit": "seconds", "visible": True, "source": "chart_drawing"}}


def test_painted_drawings_reach_the_model_as_one_explained_table(tmp_path):
    from copenet.core.market.chart_workspace.model_tables import format_context
    store, context, _ = _scene(tmp_path, count=40, extra_resources=(_drawing_reads, _avwap_column))

    payload = store.context_payload(context)
    text = format_context(payload)

    assert text.startswith("Packet layout")
    guide, table = text.split("Drawings. ", 1)[1].split("```csv\n", 1)
    for taught in ("owner=you", "perBar", "atLast", "vsClosePct", "never calendar days", "extends"):
        assert taught in guide, f"the reading guide must explain {taught}"
    header, first, second = table.split("\n```", 1)[0].split("\n")
    # Columns nobody used are dropped, floats are two decimals, and edit authority is joined in.
    assert header == "n,kind,owner,color,label,t1,p1,t2,p2,extends,perBar,atLast,vsClosePct,detail"
    assert first.startswith("1,ray,you,red,,") and ",0.05,101.95," in first
    assert "101.12" in second and "101.123456" not in text
    # An anchored VWAP is a study over the candles, so its series is a column of the one matrix.
    assert payload["samples"][-1]["metadata"]["columns"]["avwap"] == {"resource": "indicator:avwap", "field": "value"}


def test_drawing_table_stays_cheap_enough_to_always_send(tmp_path):
    from copenet.core.harness.token_count import count_text_tokens
    from copenet.core.market.chart_workspace.drawing_reads import GUIDE, drawing_table, format_drawing_table
    rows = [{"id": f"object-{index:02d}-abcdef", "kind": "trendline", "owner": "you", "color": "red", "label": "",
             "t1": 1_700_000_000 + index * 86_400, "p1": 100.25 + index, "t2": 1_702_000_000 + index * 86_400, "p2": 140.5 + index,
             "extends": "none", "perBar": 0.31, "atLast": 151.2, "vsClosePct": -2.4} for index in range(20)]

    text = format_drawing_table(drawing_table(rows, [], "session"))

    per_drawing = (count_text_tokens(text) - count_text_tokens(GUIDE)) / len(rows)
    assert per_drawing < 45, f"{per_drawing:.0f} tokens per drawing"
    assert count_text_tokens(GUIDE) < 400
