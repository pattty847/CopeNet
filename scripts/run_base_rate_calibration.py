"""Offline calibration: backtest soft_bottoming/8w over a broad universe, save the base-rate table.
Run: uv run python scripts/run_base_rate_calibration.py
"""
import json
from datetime import datetime, timezone

from copenet.core.market.base_rates import build_base_rate, save_base_rate
from copenet.core.market.replay import generate_soft_bottoming_events
from copenet.core.market.universe import UNIVERSE

HORIZON = 8
watch = [a.symbol for a in UNIVERSE if a.role in {"holding", "watch", "spec", "sector"}]
# drawdown-prone liquid basket → more independent soft-bottoming episodes = honest n
extra = ["AAPL", "MSFT", "AMD", "META", "NFLX", "DIS", "PYPL", "SHOP", "ROKU", "UBER", "ABNB",
         "COIN", "SNAP", "F", "BAC", "CSCO", "QCOM", "MU", "CRM", "NKE", "SBUX", "TGT", "PFE", "BA"]
universe = sorted(set(watch + extra))
print(f"[calibration] universe n={len(universe)}", flush=True)

events = generate_soft_bottoming_events(universe, horizon_weeks=HORIZON, period="8y")
print(f"[calibration] soft_bottoming episodes: {len(events)}", flush=True)

rate = build_base_rate(
    events, pattern="soft_bottoming", horizon_weeks=HORIZON,
    universe_id="watch+drawdown_basket", generated_at=datetime.now(timezone.utc).isoformat(),
)
path = save_base_rate(rate)
print(f"[calibration] saved {path}", flush=True)
print("[calibration] HEADLINE:", rate.headline(), flush=True)
print(json.dumps(rate.to_dict(), indent=2), flush=True)
