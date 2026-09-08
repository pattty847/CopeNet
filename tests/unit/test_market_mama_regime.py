from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd

from copenet.core.market import mama_regime as regime_module
from copenet.core.market.mama_regime import (
    ABOVE,
    BELOW,
    UNAVAILABLE,
    UNREADABLE,
    WARMING_UP,
    _bars_payload,
    mama_regime,
    mama_regimes,
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


def test_batching_a_universe_gives_every_symbol_its_solo_answer() -> None:
    """The sweep and the ticker page must never disagree about the same symbol."""
    frames = {
        "RISING": _weekly_frame([2.0] * 120),
        "FALLING": _weekly_frame([2.0] * 60 + [-4.0] * 60),
        "CHOPPY": _weekly_frame([3.0, -3.0] * 60),
        "SHORT": _weekly_frame([1.0] * 3),
    }

    batched = mama_regimes(frames)

    assert batched == {symbol: mama_regime(frame) for symbol, frame in frames.items()}
    assert batched["RISING"] == ABOVE
    assert batched["FALLING"] == BELOW


def test_a_universe_sweep_is_chunked_instead_of_one_process_per_symbol(monkeypatch) -> None:
    calls: list[int] = []
    real = regime_module.evaluator_request

    def counted(payload):
        calls.append(len(payload["requests"]))
        return real(payload)

    monkeypatch.setattr(regime_module, "evaluator_request", counted)
    monkeypatch.setattr(regime_module, "_CHUNK_BUDGET_BYTES", 40_000)
    frames = {f"SYM{index}": _weekly_frame([1.0, -0.5] * 60) for index in range(24)}

    states = mama_regimes(frames)

    assert len(states) == 24
    assert 1 < len(calls) < 24, f"expected a few chunks, got {len(calls)} calls of {calls}"
    assert sum(calls) == 24


def test_one_rejected_symbol_does_not_remove_the_rest_from_the_sweep(monkeypatch) -> None:
    """A breadth count reads its denominator off this result, so a bad frame must not
    silently take its neighbours out of the batch with it."""

    def one_bad(payload):
        return {
            "results": [
                {"key": row["key"], "t": 1, "values": {"mama": {"mama": 2.0, "fama": 1.0}}, "error": None}
                if row["key"] != "BAD"
                else {"key": "BAD", "t": None, "values": {}, "error": "Candles must be strictly ordered"}
                for row in payload["requests"]
            ]
        }

    monkeypatch.setattr(regime_module, "evaluator_request", one_bad)
    states = mama_regimes({name: _weekly_frame([1.0] * 60) for name in ("GOOD", "BAD", "ALSO_GOOD")})

    assert states == {"GOOD": ABOVE, "BAD": UNREADABLE, "ALSO_GOOD": ABOVE}


def test_an_unavailable_evaluator_marks_the_whole_chunk_and_invents_nothing(monkeypatch) -> None:
    def unavailable(_payload):
        raise ValueError("Indicator evaluator unavailable")

    monkeypatch.setattr(regime_module, "evaluator_request", unavailable)
    states = mama_regimes({name: _weekly_frame([1.0] * 60) for name in ("A", "B")})

    assert states == {"A": UNAVAILABLE, "B": UNAVAILABLE}
    assert not {ABOVE, BELOW} & set(states.values())
