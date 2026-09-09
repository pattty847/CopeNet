"""Whole-viewport chart context stays useful and honest under tight budgets."""
from __future__ import annotations

from copenet.core.market.chart_workspace import ChartStore
from copenet.core.market.chart_workspace.requests import ReadRequest

INSTRUMENT = {
    "instrumentId": "test:SYN", "symbol": "SYN", "assetClass": "equity",
    "source": "synthetic", "currency": "USD",
}


def _scene(tmp_path, *, count: int = 800):
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
