"""Publish a full-market brief from already acquired data, without another sweep."""
from __future__ import annotations
import logging
from datetime import datetime
from typing import Any
from copenet.core.pulse import PulseRecord
from ..brief import build_morning_brief, compute_movers
from ..ledger import record_screen_claims, resolve_due_claims

_LOG = logging.getLogger(__name__)


async def publish_brief(runtime, previous, provider, pulse_store, *, universe):
    current = runtime.store.load_dashboard_wire()
    brief_date = datetime.now().strftime("%Y-%m-%d")
    try:
        # Prices are fresh — score any forward-ledger claims that just came due, BEFORE
        # the chained model read so its track-record line is current.
        resolve_due_claims(runtime.store)
    except Exception:
        _LOG.warning("morning sweep: ledger resolution failed", exc_info=True)
    movers, movers_label = compute_movers(runtime.store, universe=universe)
    brief = build_morning_brief(
        previous,
        current,
        movers=movers,
        movers_label=movers_label,
        brief_date=brief_date,
    )
    wire = brief.to_wire()
    runtime.store.save_morning_brief(wire)
    try:
        # The screens make their claims the moment they fire, so the ledger can score the
        # rules the operator tunes on the same footing as the model.
        screen_claims = record_screen_claims(runtime.store, previous, current)
        if screen_claims:
            _LOG.info("morning sweep: logged %d screen claim(s) to the forward ledger", screen_claims)
    except Exception:
        _LOG.warning("morning sweep: screen claim capture failed", exc_info=True)
    _LOG.info("morning sweep: brief for %s — %s", brief_date, brief.headline)

    if pulse_store is not None:
        try:
            _publish_pulse(pulse_store, wire)
        except Exception:
            _LOG.warning("morning sweep: pulse publish failed", exc_info=True)

    if provider is not None:
        try:
            await runtime.interpret(provider, target="market")
        except Exception:
            # The deterministic brief still stands; the model read stays stale.
            _LOG.warning("morning sweep: chained model read failed", exc_info=True)
    return wire


def _publish_pulse(pulse_store, wire: dict[str, Any]) -> None:
    brief_date = str(wire.get("briefDate") or datetime.now().strftime("%Y-%m-%d"))
    pulse_id = f"market-brief-{brief_date}"
    existing = pulse_store.get(pulse_id)
    if existing is not None and existing.status != "new":
        return  # the operator already acted on today's item — don't resurrect it
    new_evidence = wire.get("newEvidence") or []
    flips = wire.get("signalFlips") or []
    now = datetime.now().astimezone().isoformat()
    record = PulseRecord(
        pulse_id=pulse_id,
        status="new",
        title=f"Morning market brief · {brief_date}",
        summary=str(wire.get("headline") or "Morning market brief is ready."),
        why_now=(
            f"Market sweep found {len(new_evidence)} new SEC filing(s) and "
            f"{len(flips)} signal flip(s) since the previous sweep."
        ),
        source_session_keys=["market-sentinel"],
        source_run_ids=[],
        created_at=existing.created_at if existing else now,
        updated_at=now,
    )
    if existing is None:
        pulse_store.create(record)
    else:
        pulse_store.save(record)  # a fresher same-day sweep updates the unread item in place
