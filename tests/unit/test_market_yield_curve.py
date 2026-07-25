from __future__ import annotations

import pandas as pd

from copenet.core.market import yield_curve
from copenet.core.market.data_sources import parse_treasury_par_yield_xml
from copenet.core.market.yield_curve import fetch_treasury_yield_curve


def test_yield_curve_builds_points_spreads_and_shape(monkeypatch) -> None:
    dates = pd.date_range("2026-07-13", periods=6, tz="UTC")
    frame = pd.DataFrame(
        [
            [3.75, 4.00, 4.20, 4.45, 4.95],
            [3.74, 4.02, 4.21, 4.46, 4.96],
            [3.73, 4.04, 4.22, 4.48, 4.98],
            [3.72, 4.06, 4.24, 4.50, 5.00],
            [3.71, 4.08, 4.26, 4.52, 5.03],
            [3.70, 4.10, 4.28, 4.55, 5.06],
        ],
        index=dates,
        columns=["BC_3MONTH", "BC_2YEAR", "BC_5YEAR", "BC_10YEAR", "BC_30YEAR"],
    )
    monkeypatch.setattr(yield_curve, "_history_cache", None)
    monkeypatch.setattr(yield_curve, "fetch_treasury_par_yield_history", lambda year: frame)
    payload = fetch_treasury_yield_curve("1w")

    assert [point["label"] for point in payload["points"]] == ["3M", "2Y", "5Y", "10Y", "30Y"]
    assert payload["points"][0]["changeBps"] == -5.0
    assert payload["spreads"][0] == {"label": "10Y–2Y", "valueBps": 45.0}
    assert payload["shape"]["label"] == "Normal · Bear steepening"
    assert payload["source"] == "us-treasury"
    assert payload["asOf"] == "2026-07-18T00:00:00Z"
    assert payload["comparisonAsOf"] == "2026-07-13T00:00:00Z"


def test_yield_curve_uses_latest_common_observation(monkeypatch) -> None:
    dates = pd.date_range("2026-07-13", periods=3, tz="UTC")
    frame = pd.DataFrame(
        [[3.7, 4.0, 4.2, 4.5, 5.0], [3.8, 4.1, 4.3, 4.6, 5.1], [3.9, 4.2, 4.4, 4.7, None]],
        index=dates,
        columns=["BC_3MONTH", "BC_2YEAR", "BC_5YEAR", "BC_10YEAR", "BC_30YEAR"],
    )
    monkeypatch.setattr(yield_curve, "_history_cache", None)
    monkeypatch.setattr(yield_curve, "fetch_treasury_par_yield_history", lambda year: frame)
    payload = fetch_treasury_yield_curve("1d")

    assert payload["asOf"] == "2026-07-14T00:00:00Z"
    assert [point["yield"] for point in payload["points"]] == [3.8, 4.1, 4.3, 4.6, 5.1]


def test_treasury_xml_parser_normalizes_cmt_fields() -> None:
    payload = b'''<feed xmlns:d="http://schemas.microsoft.com/ado/2007/08/dataservices"
        xmlns:m="http://schemas.microsoft.com/ado/2007/08/dataservices/metadata"
        xmlns="http://www.w3.org/2005/Atom"><entry><content><m:properties>
        <d:NEW_DATE>2026-07-17T00:00:00</d:NEW_DATE><d:BC_3MONTH>3.67</d:BC_3MONTH>
        <d:BC_2YEAR>3.89</d:BC_2YEAR><d:BC_10YEAR>4.42</d:BC_10YEAR>
        <d:BC_30YEARDISPLAY>4.99</d:BC_30YEARDISPLAY>
        </m:properties></content></entry></feed>'''

    frame = parse_treasury_par_yield_xml(payload)

    assert frame.index[0].isoformat() == "2026-07-17T00:00:00+00:00"
    assert frame.iloc[0].to_dict() == {"BC_3MONTH": 3.67, "BC_2YEAR": 3.89, "BC_10YEAR": 4.42}
