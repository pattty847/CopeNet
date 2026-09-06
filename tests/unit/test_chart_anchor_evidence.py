"""Anchor-to-evidence verification. Synthetic market data only."""

import pytest

from copenet.core.market.chart_workspace import ChartStore

INSTRUMENT = {"instrumentId": "test:SYN", "symbol": "SYN", "assetClass": "equity",
              "source": "synthetic", "currency": None}

# One candle that traded 41.0-43.0 and closed at 42.0, plus an indicator row on the same
# timestamp so a citation can point at something that is not a price.
CANDLE = {"t": 100, "o": 41.5, "h": 43.0, "l": 41.0, "c": 42.0, "v": 1000.0}


@pytest.fixture
def scene(tmp_path):
    store = ChartStore(tmp_path / "chart.sqlite3")
    document = store.workspace("primary", INSTRUMENT)["document"]
    capture = {
        "schemaVersion": 1, "viewId": "view-test", "viewRevision": 1, "instrument": INSTRUMENT,
        "timeframe": "D", "range": "1Y",
        "viewport": {"from": 100, "to": 100, "logicalFrom": 0.0, "logicalTo": 1.0},
        "selection": None, "settings": {"includeAccountContext": False},
        "resources": [
            {"key": "candles:D", "kind": "candles", "label": "Synthetic candles", "unit": "USD",
             "status": "loaded", "rows": [CANDLE],
             "metadata": {"priceBasis": "split_adjusted", "timeframe": "D"}},
            {"key": "indicator:rsi#1", "kind": "indicator", "label": "RSI", "unit": None,
             "status": "loaded", "rows": [{"t": 100, "value": 61.4}],
             "metadata": {"timeframe": "D"}},
        ],
        "documentId": document["documentId"], "documentRevision": 0,
    }
    observation = store.capture("session-test", "capture-test", capture)
    context = store.resolve_context("session-test", "run-test", {
        "observationId": observation["observationId"], "documentId": document["documentId"],
        "viewId": "view-test", "detail": "balanced", "access": "annotate",
    })
    return store, document, observation, context


def _request(document, observation, anchor, *, resource_key="candles:D", operation_id="op-1"):
    return {"documentId": document["documentId"], "expectedRevision": 0, "operationId": operation_id,
            "operations": [{"kind": "create", "object": {
                "id": "level-one", "kind": "level", "anchors": [anchor], "timeframe": "D",
                "label": "Synthetic level", "color": "#abcdef", "visible": True,
                "rationale": "synthetic", "evidence": [{
                    "observationId": observation["observationId"],
                    "resourceKey": resource_key, "from": 100}],
            }}]}


def _anchor(store, document, observation, context, anchor, **kwargs):
    receipt = store.apply(_request(document, observation, anchor, **kwargs), context)
    return receipt["document"]["objects"][0]["anchors"][0]


def test_an_anchor_declaring_its_source_field_is_verified_against_it(scene) -> None:
    store, document, observation, context = scene

    anchor = _anchor(store, document, observation, context,
                     {"t": 100, "value": 43.0, "evidenceField": "h"})

    assert anchor["verified"] == "exact"


def test_an_anchor_that_contradicts_its_declared_field_is_refused(scene) -> None:
    """Declaring the field is a precise claim, so it is enforced rather than recorded.

    Before verification existed, this drawing was accepted: it cited the candle, read as
    rigorous, and asserted a number the citation did not contain."""
    store, document, observation, context = scene

    with pytest.raises(ValueError, match="does not match the cited candle's h of 43.0"):
        _anchor(store, document, observation, context,
                {"t": 100, "value": 38.4, "evidenceField": "h"})


def test_an_undeclared_anchor_inside_its_cited_candle_records_in_range(scene) -> None:
    store, document, observation, context = scene

    anchor = _anchor(store, document, observation, context, {"t": 100, "value": 42.5})

    assert anchor["verified"] == "in-range"


def test_an_undeclared_anchor_outside_its_cited_candle_is_recorded_not_rejected(scene) -> None:
    """A projected target citing the base it was measured from is legitimate and sits
    outside that bar. The document says the citation does not contain it; it does not
    pretend to know the annotation is wrong."""
    store, document, observation, context = scene

    anchor = _anchor(store, document, observation, context, {"t": 100, "value": 38.4})

    assert anchor["verified"] == "out-of-range"


def test_a_drawing_cannot_certify_its_own_anchor(scene) -> None:
    """Same reason `owner` is stamped server-side: the caller does not get a vote."""
    store, document, observation, context = scene

    anchor = _anchor(store, document, observation, context,
                     {"t": 100, "value": 38.4, "verified": "exact"})

    assert anchor["verified"] == "out-of-range"


def test_citing_an_indicator_leaves_a_price_anchor_unchecked_rather_than_failing_it(scene) -> None:
    """RSI 61.4 is not comparable to a price of 42.0. An indicator is a reason to draw
    something, not a source for the level, so the anchor is honestly unverified."""
    store, document, observation, context = scene

    anchor = _anchor(store, document, observation, context, {"t": 100, "value": 42.0},
                     resource_key="indicator:rsi#1")

    assert anchor["verified"] == "unchecked"
