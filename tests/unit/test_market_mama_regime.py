from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd

from copenet.core.market import mama_regime as regime_module
from copenet.core.market.mama_regime import (
    ABOVE,
    BELOW,
    UNAVAILABLE,
    WARMING_UP,
    _bars_payload,
    mama_regime,
)


def _weekly_frame(deltas: list[float], *, unit: str = "s") -> pd.DataFrame:
    rows = []
    price = 100.0
    start = datetime(2015, 1, 4, tzinfo=timezone.utc)
    for index, delta in enumerate(deltas):
        close = price + delta
        rows.append(
            {
                "date": start + timedelta(days=index * 7),
                "open": price,
                "high": max(price, close) + 1,
                "low": min(price, close) - 1,
                "close": close,
                "volume": 1_000_000.0,
            }
        )
        price = close
    frame = pd.DataFrame(rows)
    frame["date"] = frame["date"].astype(f"datetime64[{unit}, UTC]")
    return frame


def test_bars_payload_reads_epoch_seconds_at_any_datetime_resolution() -> None:
    """A hardcoded nanosecond divisor silently zeroes every second-resolution frame.

    pandas hands back datetime64[s] or [ns] depending on how the column was built. When
    that difference reached the ordering guard it kept the first bar and discarded the
    rest, so every symbol reported `warming up` while looking entirely healthy upstream.
    """
    deltas = [1.0, -0.5] * 30
    seconds = _bars_payload(_weekly_frame(deltas, unit="s"))
    nanoseconds = _bars_payload(_weekly_frame(deltas, unit="ns"))

    assert seconds == nanoseconds
    assert len(seconds) == len(deltas)
    assert seconds[0]["t"] == int(datetime(2015, 1, 4, tzinfo=timezone.utc).timestamp())
    assert all(later["t"] > earlier["t"] for earlier, later in zip(seconds, seconds[1:]))


def test_mama_regime_reports_the_chart_registry_state_over_full_history() -> None:
    rising = mama_regime(_weekly_frame([2.0] * 120))
    falling = mama_regime(_weekly_frame([2.0] * 60 + [-4.0] * 60))

    assert rising == ABOVE
    assert falling == BELOW


def test_mama_regime_says_warming_up_rather_than_guessing_through_the_settling_region() -> None:
    assert mama_regime(_weekly_frame([1.0] * 4)) == WARMING_UP
    assert mama_regime(pd.DataFrame()) == WARMING_UP


def test_mama_regime_reports_unavailable_instead_of_falling_back_to_an_approximation(
    monkeypatch,
) -> None:
    """The bug this module replaced was an EMA wearing MAMA's name. A silent fallback
    when the evaluator is missing would reintroduce exactly that."""

    def unavailable(_payload):
        raise ValueError("Indicator evaluator unavailable")

    monkeypatch.setattr(regime_module, "evaluator_request", unavailable)
    result = mama_regime(_weekly_frame([1.0] * 120))

    assert result == UNAVAILABLE
    assert result not in {ABOVE, BELOW}
