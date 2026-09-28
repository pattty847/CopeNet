"""Publish a full-market brief from already acquired data, without another sweep."""
from __future__ import annotations
import logging
from datetime import datetime
from ..brief import build_morning_brief, compute_movers
from ..ledger import record_screen_claims, resolve_due_claims

_LOG = logging.getLogger(__name__)


async def publish_brief(runtime, previous, provider, *, universe):
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

    if provider is not None:
        try:
            await runtime.interpret(provider, target="market")
        except Exception:
            # The deterministic brief still stands; the model read stays stale.
            _LOG.warning("morning sweep: chained model read failed", exc_info=True)
    return wire
