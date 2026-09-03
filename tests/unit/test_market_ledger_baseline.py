"""Baseline comparisons must use the prices available to the recorded claims."""

from datetime import datetime, timezone
from pathlib import Path

from copenet.core.market.ledger import HorizonSlot, LedgerClaim, LedgerStore
from copenet.core.market.ledger_report import _CloseLookup, ledger_report
from copenet.core.market.models import MarketBar
from copenet.core.market.store import MarketStore


def bars(store: MarketStore, symbol: str, values: dict[str, float]) -> None:
    store.save_bars(symbol, "daily", [
        MarketBar(t=int(datetime.fromisoformat(day).replace(tzinfo=timezone.utc).timestamp()), o=value, h=value, l=value, c=value, v=100)
        for day, value in values.items()
    ])


def setup(tmp_path: Path) -> tuple[MarketStore, LedgerClaim]:
    store = MarketStore(tmp_path)
    bars(store, "AAA", {"2026-08-03": 100, "2026-08-04": 120, "2026-08-31": 110, "2026-09-01": 160})
    bars(store, "VOO", {"2026-08-03": 100, "2026-08-04": 100, "2026-08-31": 100, "2026-09-01": 100})
    claim = LedgerClaim(
        claim_id="synthetic", created_at="2026-08-04T12:00:00Z", kind="lean", target="AAA",
        value="bullish", confidence=None, model="test", note="Synthetic premarket claim",
        snapshot_price=100, snapshot_voo=100,
        horizons={"4w": HorizonSlot(due_at="2026-09-01T12:00:00Z", resolved_at="2026-09-01T12:00:00Z", price=110, voo=100, return_pct=10, excess_pct=10, outcome="correct")},
    )
    LedgerStore(store).save([claim])
    return store, claim


def baseline(store: MarketStore) -> dict:
    return ledger_report(store, baseline_universe=["AAA"])["baseline"]["lean"]["4w"]


def test_premarket_baseline_uses_previous_completed_sessions_at_both_ends(tmp_path: Path) -> None:
    store, _ = setup(tmp_path)
    result = baseline(store)
    assert result["pct"] == result["accuracyPct"] == 100
    assert result["matchedClaims"] == result["scoredClaims"] == 1
    # Later changes to today's provisional/final bar must not revise a premarket window.
    bars(store, "AAA", {"2026-08-03": 100, "2026-08-04": 120, "2026-08-31": 110, "2026-09-01": 50})
    assert baseline(store) == result


def test_close_availability_observes_new_york_dst_and_weekends(tmp_path: Path) -> None:
    store = MarketStore(tmp_path)
    bars(store, "AAA", {"2026-01-08": 100, "2026-01-09": 110, "2026-08-03": 120, "2026-08-04": 130})
    lookup = _CloseLookup(store)
    assert lookup.at("AAA", "2026-01-09T20:59:00Z") == 100
    assert lookup.at("AAA", "2026-01-09T21:00:00Z") == 110
    assert lookup.at("AAA", "2026-01-12T12:00:00Z") == 110
    assert lookup.at("AAA", "2026-08-04T19:59:00Z") == 120
    assert lookup.at("AAA", "2026-08-04T20:00:00Z") == 130


def test_after_close_claim_uses_same_session_when_recorded_prices_match(tmp_path: Path) -> None:
    store, claim = setup(tmp_path)
    claim.created_at = "2026-08-04T21:00:00Z"
    claim.snapshot_price = 120
    slot = claim.horizons["4w"]
    slot.resolved_at = "2026-09-01T21:00:00Z"
    slot.price = 160
    slot.return_pct = 33.33
    LedgerStore(store).save([claim])
    assert baseline(store)["pct"] == 100


def test_intraday_snapshots_are_not_replaced_by_later_final_closes(tmp_path: Path) -> None:
    store, claim = setup(tmp_path)
    claim.created_at = "2026-08-04T17:00:00Z"
    claim.snapshot_price = 115  # Partial candle not reconstructable from finalized dailies.
    LedgerStore(store).save([claim])
    assert baseline(store)["pct"] is None
    assert baseline(store)["matchedClaims"] == 0
    assert ledger_report(store)["stats"]["lean"]["4w"]["correct"] == 1


def test_baseline_delta_uses_the_matched_cohort_not_all_claims(tmp_path: Path) -> None:
    store, claim = setup(tmp_path)
    unmatched = LedgerClaim.from_json(claim.to_json())
    unmatched.claim_id = "unmatched"
    unmatched.snapshot_price = 115
    unmatched.horizons["4w"].outcome = "incorrect"
    LedgerStore(store).save([claim, unmatched])
    result = baseline(store)
    assert (result["matchedClaims"], result["scoredClaims"]) == (1, 2)
    assert result["accuracyPct"] == 100
    assert ledger_report(store)["stats"]["lean"]["4w"]["accuracyPct"] == 50


def test_missing_universe_history_does_not_silently_change_the_dart_population(tmp_path: Path) -> None:
    store, _ = setup(tmp_path)
    result = ledger_report(store, baseline_universe=["AAA", "MISSING"])["baseline"]["lean"]["4w"]
    assert result["pct"] is None
    assert result["matchedClaims"] == 0


def test_baseline_uses_the_same_return_rounding_as_recorded_outcomes(tmp_path: Path) -> None:
    store, claim = setup(tmp_path)
    bars(store, "AAA", {"2026-08-03": 100, "2026-08-31": 100.004})
    slot = claim.horizons["4w"]
    slot.price, slot.return_pct, slot.excess_pct, slot.outcome = 100.004, 0, 0, "incorrect"
    LedgerStore(store).save([claim])
    assert baseline(store)["pct"] == baseline(store)["accuracyPct"] == 0


def test_regime_baseline_excludes_unscoreable_event_risk_windows(tmp_path: Path) -> None:
    store, claim = setup(tmp_path)
    claim.kind, claim.target, claim.value = "regime", "VOO", "chop"
    claim.horizons["4w"].return_pct = 0
    unscoreable = LedgerClaim.from_json(claim.to_json())
    unscoreable.claim_id, unscoreable.value = "unscoreable", "event-risk"
    unscoreable.horizons["4w"].outcome = "unscoreable"
    unscoreable.horizons["4w"].return_pct = 20
    LedgerStore(store).save([claim, unscoreable])
    result = ledger_report(store)["baseline"]["regime"]["4w"]
    assert result["label"] == "always chop"
    assert result["pct"] == 100
    assert result["matchedClaims"] == result["scoredClaims"] == 1
