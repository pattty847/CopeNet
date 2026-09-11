"""Pure setup eligibility. Ranks describe a metric, never a probability or trade recommendation."""
from .models import PRESETS, ScreenerConfig


def distance(price, reference):
    return (price / reference - 1) * 100 if reference is not None and reference > 0 else None


def enrich(row):
    price = row["price"]
    upper, lower = row["bandUpper"], row["bandLower"]
    return {**row, "dollarVolume": price * row["averageVolume"],
            "distance50": distance(price, row["sma50"]), "distance200": distance(price, row["sma200"]),
            "drawdown": distance(price, row["high52"]),
            "bandWidth": (upper - lower) / price * 100 if upper is not None and lower is not None and upper >= lower > 0 else None}


def evaluate(source: dict, config: ScreenerConfig) -> dict:
    eligible = []
    excluded = {"instrument": source["invalid"], "missingEligibility": 0, "outsideUniverse": 0}
    for row in source["rows"]:
        if row["type"] != "stock" or row["subtype"] != "common":
            excluded["instrument"] += 1
            continue
        cap, price, volume = row["marketCap"], row["price"], row["averageVolume"]
        if any(value is None or value <= 0 for value in (cap, price, volume)):
            excluded["missingEligibility"] += 1
            continue
        if cap < config.minCap or (config.maxCap is not None and cap > config.maxCap) or price < config.minPrice or price * volume < config.minDollarVolume:
            excluded["outsideUniverse"] += 1
            continue
        eligible.append(enrich(row))
    screens = []
    for preset in PRESETS:
        matches, missing = [], 0
        for row in eligible:
            result = match(preset["id"], row)
            if result is None:
                missing += 1
            elif result:
                matches.append({**row, "direction": ("Bullish" if row["change"] > 0 else "Bearish") if preset["id"] == "expansion" else preset["direction"]})
        metric = preset["metric"]
        matches.sort(key=lambda row: (row[metric] if preset["ascending"] else -row[metric], row["id"]))
        screens.append({"id": preset["id"], "rows": matches, "missingFields": missing})
    return {"eligible": len(eligible), "excluded": excluded, "screens": screens}


def match(identifier, row):
    required = {
        "compression": ["bandWidth", "drawdown", "rsi"],
        "pullback": ["sma50", "sma200", "distance50", "drawdown", "rsi"],
        "oversold": ["drawdown", "rsi"],
        "breakdown": ["sma50", "sma200", "distance200", "rsi", "monthReturn"],
        "expansion": ["relativeVolume", "change"],
    }[identifier]
    if any(row[key] is None for key in required):
        return None
    if identifier == "compression":
        return row["bandWidth"] <= 10 and -10 <= row["drawdown"] <= 0 and 40 <= row["rsi"] <= 65
    if identifier == "pullback":
        return row["price"] > row["sma200"] and row["sma50"] > row["sma200"] and -2 <= row["distance50"] <= 4 and -15 <= row["drawdown"] <= -3 and 40 <= row["rsi"] <= 60
    if identifier == "oversold":
        return row["marketCap"] >= 15e9 and -40 <= row["drawdown"] <= -15 and 25 <= row["rsi"] <= 38
    if identifier == "breakdown":
        return row["price"] < row["sma50"] < row["sma200"] and 30 <= row["rsi"] <= 48 and row["monthReturn"] < 0 and row["distance200"] >= -15
    return row["relativeVolume"] >= 1.5 and 2 <= abs(row["change"]) <= 10
