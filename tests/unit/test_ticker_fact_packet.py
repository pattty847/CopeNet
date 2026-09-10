"""Ticker packets retain evidence, units and missing-data distinctions."""
from dataclasses import replace
import numpy as np
import pandas as pd
import pytest
from copenet.core.market.features import compute_features
from copenet.core.market.ticker_fact_packet import ticker_fact_packet
from test_market_interpretation import _base_rate


def features(count=160, volume=1000):
    prices = np.linspace(50, 100, count)
    return compute_features(pd.DataFrame({"date": pd.date_range("2020-01-06", periods=count, freq="W-MON"),
        "open": prices, "high": prices * 1.01, "low": prices * .99, "close": prices, "volume": volume}), symbol="TEST", basis="split_adjusted")


def test_sparse_packet_keeps_quality_and_missing_evidence_explicit():
    packet = ticker_fact_packet(features(3, 0), name="Synthetic", base_rate=None)
    assert "THIN HISTORY" in packet and "no volume data" in packet
    assert "basis split_adjusted" in packet
    assert "FUNDAMENTALS: not available" in packet
    assert "do not invent headlines" in packet
    assert "52w +0.0%" not in packet


@pytest.mark.parametrize("eps", [0.0, -1.0])
def test_nonpositive_eps_does_not_claim_a_meaningful_pe(eps):
    packet = ticker_fact_packet(features(), name="Synthetic", base_rate=None, fundamentals={"epsTtm": eps, "peTtm": None})
    assert "non-positive" in packet and "P/E not meaningful" in packet
    assert "no usable revenue/EPS" not in packet


def test_full_packet_preserves_section_order_limits_and_provenance():
    fs = replace(features(), soft_bottoming=True, excess_13w=0.0, compression=True, compression_shape="symmetrical", range_ratio_12v36=.5)
    packet = ticker_fact_packet(fs, name="Synthetic", base_rate=_base_rate(),
        verdict=[{"bench":"BENCH", "label":"Beats", "excess_return_pct":None}],
        evidence=[{"type":"SEC", "headline":f"evidence-{i}", "source":"filing"} for i in range(6)],
        fundamentals={"epsTtm":2.0, "peTtm":25.0, "revenueQuarterly":[{"period":f"quarter-{i}","value":1e9,"yoy_pct":.1} for i in range(5)]},
        news=[{"title":f"news-{i}","url":"https://example.com/article","snippet":"x"*200} for i in range(6)],news_source="search")
    labels = ["ASSET:", "DATA QUALITY:", "RETURNS:", "TREND:", "STRUCTURE", "RANGE BEHAVIOR:", "RISK STATE:", "RELATIVE:", "VOLUME:", "PATTERN", "BENCHMARK CHECK", "EVIDENCE:", "FUNDAMENTALS", "VALUATION:", "RECENT WEB/NEWS"]
    offsets = [packet.index(label) for label in labels]
    assert offsets == sorted(offsets)
    assert "n=5" in packet and "insufficient overlapping history" in packet
    assert "evidence-5" not in packet and "news-5" not in packet and "quarter-4" not in packet
    assert "$1.00B, YoY +10.0%" in packet and "25.0x (TTM EPS $2.00)" in packet
    assert "[search]" in packet and "example.com" in packet and "x" * 181 not in packet
    assert "Calibrated base rate" not in ticker_fact_packet(fs, name="Synthetic", base_rate=replace(_base_rate(), n=4))
