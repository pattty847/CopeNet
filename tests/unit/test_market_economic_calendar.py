from __future__ import annotations

from datetime import date, datetime, timezone

from copenet.core.market.economic_calendar import _normalize_events, load_economic_calendar


def test_normalize_events_filters_low_impact_and_sorts() -> None:
    rows = [
        {"CalendarId": "late", "Date": "2026-07-13T14:00:00", "Event": "Consumer Expectations", "Importance": 2},
        {
            "CalendarId": "high",
            "Date": "2026-07-13T12:30:00Z",
            "Country": "United States",
            "Category": "Inflation",
            "Event": "CPI YoY",
            "Importance": 3,
            "Actual": "3.1%",
            "Forecast": "2.8%",
            "Previous": "2.7%",
            "SourceURL": "https://www.bls.gov/cpi/",
        },
        {"CalendarId": "low", "Date": "2026-07-13T11:00:00Z", "Event": "Minor release", "Importance": 1},
        {"CalendarId": "outside", "Date": "2026-08-13T11:00:00Z", "Event": "Outside window", "Importance": 3},
    ]

    events = _normalize_events(rows, start=date(2026, 7, 11), end=date(2026, 7, 18))

    assert [event["id"] for event in events] == ["high", "late"]
    assert events[0]["actual"] == "3.1%"
    assert events[0]["sourceUrl"] == "https://www.bls.gov/cpi/"
    assert events[1]["date"].endswith("Z")


async def test_unconfigured_calendar_returns_honest_empty_state(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("TRADING_ECONOMICS_API_KEY", raising=False)

    payload = await load_economic_calendar(
        tmp_path,
        now=datetime(2026, 7, 11, 12, tzinfo=timezone.utc),
    )

    assert payload["configured"] is False
    assert payload["provider"] == "Trading Economics"
    assert payload["events"] == []
    assert "error" not in payload
