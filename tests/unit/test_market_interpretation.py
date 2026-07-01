"""Unit tests for the Insight Engine fact packets + interpretation parsing (no live model calls)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from copenet.core.market.base_rates import build_base_rate
from copenet.core.market.fact_packets import market_fact_packet, ticker_fact_packet
from copenet.core.market.features import compute_features
from copenet.core.market.interpretation import (
    extract_json,
    parse_market_read,
    parse_ticker_read,
)


def _base_rate():
    events = [
        {"as_of": "2021-01-01", "fwd_return": 5.0, "mae": -3.0, "beat_bench": True, "regime": "bull"},
        {"as_of": "2021-02-01", "fwd_return": -4.0, "mae": -9.0, "beat_bench": False, "regime": "bull"},
        {"as_of": "2022-03-01", "fwd_return": 8.0, "mae": -2.0, "beat_bench": True, "regime": "bear"},
        {"as_of": "2022-06-01", "fwd_return": 2.0, "mae": -6.0, "beat_bench": False, "regime": "bear"},
        {"as_of": "2023-06-01", "fwd_return": 1.0, "mae": -1.0, "beat_bench": True, "regime": "bull"},
    ]
    return build_base_rate(events, pattern="soft_bottoming", horizon_weeks=8, universe_id="t", generated_at="x")


def test_market_fact_packet_includes_key_sections():
    wire = {
        "asOf": "as of test close",
        "briefing": {"data": {"vix": 17.6, "breadthPct": 94.0}},
        "macro": {"data": [{"label": "DXY", "value": "101.3", "change": "-0.1%"}]},
        "rrg": {"data": [{"symbol": "XLK", "quadrant": "leading"}, {"symbol": "XLE", "quadrant": "improving"}]},
        "softBottoming": {"data": [{"symbol": "SOFI", "score": 0.71, "drawdown": "-38%", "rsi": "60"}]},
        "trend": {"data": [{"symbol": "SOFI", "direction": "up", "note": "weekly up", "confirmed": True}]},
        "portfolio": {"data": {"total": "$4,417", "pnl": "+731", "positions": [{"symbol": "GOOG", "pnlPct": "+69.9%"}]}},
        "speculative": {"data": [{"symbol": "SLI", "pnlPct": "-32%", "thesis": "lithium optionality"}]},
        "evidence": {"data": []},
    }
    packet = market_fact_packet(wire, _base_rate())
    assert "VIX 17.6" in packet
    assert "breadth 94%" in packet
    assert "leading: XLK" in packet
    assert "SOFI (score 0.71" in packet
    assert "n=5" in packet  # base rate quoted with sample size
    assert "GOOG +69.9%" in packet
    assert "EVIDENCE: none" in packet  # honest about missing evidence


def test_market_fact_packet_omits_base_rate_when_no_flags():
    wire = {"asOf": "x", "softBottoming": {"data": []}}
    packet = market_fact_packet(wire, _base_rate())
    assert "SOFT BOTTOMING FLAGS" not in packet
    assert "base rate" not in packet.lower()


def test_ticker_fact_packet_carries_data_quality_and_pattern():
    n = 60
    closes = list(np.linspace(100, 50, 40)) + [50, 49, 51, 50, 52, 51, 54, 53, 56, 58] + list(np.linspace(58, 66, 10))
    dates = pd.date_range("2020-01-06", periods=len(closes), freq="W-MON")
    arr = np.array(closes)
    frame = pd.DataFrame({"date": dates, "open": arr, "high": arr * 1.01, "low": arr * 0.99, "close": arr, "volume": [1e6] * len(closes)})
    fs = compute_features(frame, symbol="TEST")
    packet = ticker_fact_packet(fs, name="Test Corp", base_rate=_base_rate(), verdict=[{"bench": "VOO", "label": "Lags"}])
    assert "ASSET: TEST (Test Corp)" in packet
    assert "DATA QUALITY" in packet
    assert "RETURNS:" in packet
    assert "vs VOO: Lags" in packet
    if fs.soft_bottoming:
        assert "SOFT BOTTOMING FIRING" in packet and "n=5" in packet


def test_extract_json_handles_fences_and_prose():
    assert extract_json('{"a": 1}') == {"a": 1}
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('Here you go:\n{"a": 1}\nHope that helps!') == {"a": 1}


def test_parse_market_read_clamps_and_truncates():
    raw = {
        "headline": "H" * 300,
        "emphasis": "H",
        "summary": "s",
        "regime": "TO THE MOON",
        "regime_reasoning": "r",
        "attention": [{"symbol": f"t{i}", "kind": "k", "why": "w"} for i in range(9)],
        "rotation_read": "rot",
        "speculative_comment": "spec",
        "thesis_killers": [{"signal": "s", "kill": "k"} for _ in range(9)],
        "caveats": "c",
    }
    import json

    read = parse_market_read(json.dumps(raw), model="gpt-5.5", generated_at="t")
    assert read.regime == "chop"  # invalid regime clamped
    assert len(read.headline) <= 160
    assert len(read.attention) == 3
    assert len(read.thesis_killers) == 4
    assert read.attention[0]["symbol"] == "T0"  # uppercased
    assert read.model == "gpt-5.5"


def test_parse_ticker_read_clamps_confidence():
    import json

    read = parse_ticker_read(
        json.dumps({"read": "r", "bull_case": "b", "bear_case": "br", "what_would_change_my_mind": "w", "confidence": "ABSOLUTE", "confidence_reason": "cr", "key_facts": ["a", "b"]}),
        model="gpt-5.5",
        generated_at="t",
    )
    assert read.confidence == "low"  # unknown confidence degrades to low, never up
    assert read.key_facts == ["a", "b"]
