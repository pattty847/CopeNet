"""Forward Ledger — claim capture, pre-registered scoring rules, calibration report."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from copenet.core.market.ledger import (
    LedgerStore,
    record_market_read_claims,
    record_ticker_read_claim,
    resolve_due_claims,
)
from copenet.core.market.ledger_report import ledger_report, track_record_line
from copenet.core.market.models import MarketBar
from copenet.core.market.store import MarketStore


def _bars(closes: list[float], *, start: int = 1_735_000_000) -> list[MarketBar]:
    return [MarketBar(t=start + i * 86_400, o=c, h=c, l=c, c=c, v=100) for i, c in enumerate(closes)]


def _store(tmp_path: Path, *, voo: float = 100.0, sofi: float = 10.0) -> MarketStore:
    store = MarketStore(tmp_path)
    store.save_bars("VOO", "daily", _bars([voo]))
    store.save_bars("SOFI", "daily", _bars([sofi]))
    return store


def _market_read_wire() -> dict:
    return {
        "regime": "risk-on",
        "regimeReasoning": "breadth 81%",
        "attention": [{"symbol": "SOFI", "kind": "spec lane", "why": "insider cluster"}],
        "model": "gpt-5.5",
    }


def test_capture_market_read_logs_regime_and_attention(tmp_path: Path) -> None:
    store = _store(tmp_path)
    added = record_market_read_claims(store, _market_read_wire())
    assert added == 2
    claims = LedgerStore(store).load()
    regime = next(c for c in claims if c.kind == "regime")
    assert regime.value == "risk-on"
    assert regime.snapshot_voo == 100.0
    assert set(regime.horizons) == {"4w", "8w"}
    attention = next(c for c in claims if c.kind == "attention")
    assert attention.target == "SOFI"
    assert attention.snapshot_price == 10.0


def test_capture_ticker_lean(tmp_path: Path) -> None:
    store = _store(tmp_path)
    added = record_ticker_read_claim(store, "sofi", {"lean": "bullish", "confidence": "high", "model": "gpt-5.5", "read": "..."})
    assert added == 1
    claim = LedgerStore(store).load()[0]
    assert (claim.kind, claim.target, claim.value, claim.confidence) == ("lean", "SOFI", "bullish", "high")


def test_capture_skips_invalid_lean(tmp_path: Path) -> None:
    store = _store(tmp_path)
    assert record_ticker_read_claim(store, "SOFI", {"lean": "to the moon"}) == 0


def _force_due(store: MarketStore) -> None:
    """Rewind every unresolved horizon's due_at into the past."""
    ledger = LedgerStore(store)
    claims = ledger.load()
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat().replace("+00:00", "Z")
    for claim in claims:
        for slot in claim.horizons.values():
            slot.due_at = past
    ledger.save(claims)


def test_resolution_scores_pre_registered_rules(tmp_path: Path) -> None:
    store = _store(tmp_path, voo=100.0, sofi=10.0)
    record_market_read_claims(store, _market_read_wire())
    record_ticker_read_claim(store, "SOFI", {"lean": "bullish", "confidence": "medium"})
    _force_due(store)

    # VOO +2% (risk-on correct), SOFI +8% (bullish correct; attention correct — abs move >= 5%)
    store.save_bars("VOO", "daily", _bars([100.0, 102.0]))
    store.save_bars("SOFI", "daily", _bars([10.0, 10.8]))
    resolved = resolve_due_claims(store)
    assert resolved == 6  # 3 claims × 2 horizons

    report = ledger_report(store)
    assert report["stats"]["regime"]["4w"] == {"correct": 1, "incorrect": 0, "push": 0, "accuracyPct": 100.0}
    assert report["stats"]["lean"]["4w"]["correct"] == 1
    assert report["stats"]["attention"]["4w"]["correct"] == 1
    assert report["pendingHorizons"] == 0


def test_resolution_chop_overlap_and_neutral_push(tmp_path: Path) -> None:
    store = _store(tmp_path, voo=100.0)
    record_market_read_claims(store, {"regime": "chop", "attention": [], "model": "m"})
    record_ticker_read_claim(store, "SOFI", {"lean": "neutral"})
    _force_due(store)
    store.save_bars("VOO", "daily", _bars([100.0, 102.0]))  # +2%: inside chop band AND >= risk-on floor
    store.save_bars("SOFI", "daily", _bars([10.0, 11.0]))
    resolve_due_claims(store)
    report = ledger_report(store)
    assert report["stats"]["regime"]["4w"]["correct"] == 1  # chop band is -3..+3
    assert report["stats"]["lean"]["4w"] == {"correct": 0, "incorrect": 0, "push": 1, "accuracyPct": None}


def test_resolution_event_risk_is_unscoreable(tmp_path: Path) -> None:
    store = _store(tmp_path)
    record_market_read_claims(store, {"regime": "event-risk", "attention": [], "model": "m"})
    _force_due(store)
    store.save_bars("VOO", "daily", _bars([100.0, 90.0]))
    resolve_due_claims(store)
    report = ledger_report(store)
    assert report["stats"]["regime"]["4w"] == {"correct": 0, "incorrect": 0, "push": 0, "accuracyPct": None}


def test_resolution_incorrect_regime(tmp_path: Path) -> None:
    store = _store(tmp_path)
    record_market_read_claims(store, {"regime": "risk-on", "attention": [], "model": "m"})
    _force_due(store)
    store.save_bars("VOO", "daily", _bars([100.0, 95.0]))  # -5%: risk-on wrong
    resolve_due_claims(store)
    assert ledger_report(store)["stats"]["regime"]["4w"]["incorrect"] == 1


def test_unresolved_claims_wait_for_horizon(tmp_path: Path) -> None:
    store = _store(tmp_path)
    record_ticker_read_claim(store, "SOFI", {"lean": "bearish"})
    assert resolve_due_claims(store) == 0  # due in 28/56 days, not now
    assert ledger_report(store)["pendingHorizons"] == 2


def test_track_record_line_needs_minimum_sample(tmp_path: Path) -> None:
    store = _store(tmp_path)
    assert track_record_line(store) is None
    for _ in range(3):
        record_market_read_claims(store, {"regime": "risk-on", "attention": [], "model": "m"})
    _force_due(store)
    store.save_bars("VOO", "daily", _bars([100.0, 102.0]))
    resolve_due_claims(store)
    line = track_record_line(store)
    assert line is not None
    assert "regime calls: 3/3 correct at 4w" in line


# ---------- screens and the baseline (added 2026-09-02) ----------

from copenet.core.market.ledger import record_screen_claims  # noqa: E402


def _wire(*, as_of: str = "2026-09-01", soft: list[dict] | None = None, trend: list[dict] | None = None, accumulation: list[dict] | None = None) -> dict:
    return {
        "asOf": as_of,
        "softBottoming": {"data": soft or []},
        "trend": {"data": trend or []},
        "accumulation": {"data": accumulation or []},
    }


def test_screen_claims_fire_only_when_a_screen_newly_fires(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.save_bars("XLK", "daily", _bars([50.0]))
    previous = _wire(
        trend=[{"symbol": "SOFI", "direction": "down", "confirmed": False}, {"symbol": "XLK", "direction": "up", "confirmed": True}],
        accumulation=[{"symbol": "SOFI", "confluence": 2}],
    )
    current = _wire(
        soft=[{"symbol": "SOFI", "score": 0.71, "drawdown": "-23%", "rsi": "38"}],
        trend=[{"symbol": "SOFI", "direction": "up", "confirmed": True}, {"symbol": "XLK", "direction": "down", "confirmed": False}],
        accumulation=[{"symbol": "SOFI", "confluence": 3, "why": "below 40w, rsi 38"}],
    )
    # First sweep never claims — everything would look new.
    assert record_screen_claims(store, {"asOf": "as of no market refresh yet"}, current) == 0
    assert record_screen_claims(store, previous, current) == 4
    claims = [c for c in LedgerStore(store).load() if c.kind == "screen"]
    assert sorted((c.signal, c.target, c.value) for c in claims) == [
        ("accumulation", "SOFI", "bullish"),
        ("soft-bottoming", "SOFI", "bullish"),
        ("trend", "SOFI", "bullish"),
        ("trend", "XLK", "bearish"),
    ]
    assert all(c.model == "screen" and c.snapshot_price for c in claims)
    # The same picture at the next sweep adds nothing; a re-fire inside the grace window is one episode.
    assert record_screen_claims(store, current, current) == 0
    assert record_screen_claims(store, previous, current) == 0


def test_screen_claims_score_like_leans_and_report_per_signal(tmp_path: Path) -> None:
    store = _store(tmp_path, sofi=10.0)
    record_screen_claims(store, _wire(), _wire(soft=[{"symbol": "SOFI", "score": 0.8, "drawdown": "-20%", "rsi": "35"}]))
    _force_due(store)
    store.save_bars("SOFI", "daily", _bars([10.0, 10.5]))
    store.save_bars("VOO", "daily", _bars([100.0, 101.0]))
    resolve_due_claims(store)
    report = ledger_report(store, baseline_universe=["SOFI"])
    assert report["stats"]["screen"]["4w"]["correct"] == 1
    assert report["signals"]["soft-bottoming"]["4w"] == {"correct": 1, "incorrect": 0, "push": 0, "accuracyPct": 100.0}
    claim = next(c for c in report["recent"] if c["kind"] == "screen")
    assert claim["signal"] == "soft-bottoming"


def test_baseline_measures_the_dart_and_the_best_constant_regime_call(tmp_path: Path) -> None:
    store = _store(tmp_path, voo=100.0, sofi=10.0)
    record_market_read_claims(store, {"regime": "risk-on", "attention": [{"symbol": "SOFI", "kind": "x", "why": "y"}], "model": "m"})
    _force_due(store)
    # Window: SOFI +8% (attention correct), a dart name XLK +1% (no move), VOO +2%.
    store.save_bars("SOFI", "daily", _bars([10.0, 10.8]))
    store.save_bars("XLK", "daily", _bars([50.0, 50.5]))
    store.save_bars("VOO", "daily", _bars([100.0, 102.0]))
    resolve_due_claims(store)
    report = ledger_report(store, baseline_universe=["SOFI", "XLK"])
    # December 2024 bars cannot reconstruct a current claim's window. Do not silently
    # call the stale price a zero return and flatter the model's comparison.
    attention = report["baseline"]["attention"]["4w"]
    assert attention == {"pct": None, "n": 2, "label": "dart over 2 tracked names", "matchedClaims": 0, "scoredClaims": 1, "accuracyPct": None}
    regime = report["baseline"]["regime"]["4w"]
    assert regime["n"] == 1 and regime["pct"] == 100.0 and regime["label"] in ("always risk-on", "always chop")
    assert report["baseline"]["screen"]["4w"]["pct"] is None  # nothing scored for screens yet
