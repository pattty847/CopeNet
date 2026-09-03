"""An inspectable asset selection; missing references block, never widen scope."""
from ..models import UniverseAsset
from ..universe import UNIVERSE, find_asset
from .definitions import symbols as validate_symbols


def resolve_scope(scan: dict, watchlists: list[dict]) -> dict:
    reasons: dict[str, list[str]] = {}
    assets = {}
    issues = []

    def include(symbol, reason, name="", role="watch"):
        reasons.setdefault(symbol, []).append(reason)
        assets.setdefault(symbol, find_asset(symbol) or UniverseAsset(symbol, name or symbol, role))

    if scan["includeUniverse"]:
        for asset in UNIVERSE:
            if asset.role != "context":
                include(asset.symbol, "Built-in market universe", asset.name, asset.role)
    by_name = {item["name"]: item for item in watchlists}
    for name in scan["watchlists"]:
        if name not in by_name:
            issues.append(f"Watchlist '{name}' was removed or renamed; select its replacement")
            continue
        try:
            validate_symbols([item["symbol"] for item in by_name[name]["entries"]], f"Watchlist '{name}'")
        except ValueError as exc:
            issues.append(str(exc))
            continue
        for item in by_name[name]["entries"]:
            include(item["symbol"], f"Watchlist · {name}", item.get("name", ""), by_name[name]["role"])
    for symbol in scan["symbols"]:
        include(symbol, "Added directly")
    for symbol in scan["excludeSymbols"]:
        reasons.pop(symbol, None)
        assets.pop(symbol, None)
    resolved = list(reasons)
    if len(resolved) > 1000:
        issues.append("Scan asset limit reached (1000); split this basket into smaller scans")
    context = ["VOO"] if "prices" in scan["sources"] and resolved and "VOO" not in resolved else []
    if not resolved and any(source in scan["sources"] for source in ("prices", "sec", "financials")):
        issues.append("Select assets for per-asset sources")
    return {"resolvedSymbols": resolved, "contextSymbols": context, "inclusions": [{"symbol": symbol, "reasons": why} for symbol, why in reasons.items()], "issues": issues, "assets": list(assets.values())}
