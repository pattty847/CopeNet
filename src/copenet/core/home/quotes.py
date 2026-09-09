"""The line CopeNet opens the day with.

One quote is chosen per calendar day, deterministically, so the page does not reshuffle on
every render or every reconnect — the operator can refer to "today's line".

Attribution is per-quote and defaults to CopeNet, because the list mixes the operator's own
material with borrowed market aphorisms. Signing Buffett's line "— CopeNet" would be a
misattribution the card states in the operator's own voice, so the borrowed ones name their
source. `ATTRIBUTED` is a dict rather than a second list so an entry can be edited or moved
without the two falling out of step.
"""

from __future__ import annotations

from datetime import date

# ---------------------------------------------------------------------------------------
# OPERATOR: this is the whole API — edit the list. Any length; the picker is modulo it.
# A quote is signed "CopeNet" unless it appears in ATTRIBUTED below.
# ---------------------------------------------------------------------------------------
QUOTES: list[str] = [
    "Discipline compounds faster than excitement.",
    "The market can stay irrational longer than you can stay solvent.",
    "Price is what you pay. Value is what you get.",
    "Risk comes from not knowing what you're doing.",

    "The trend is your friend until it files a restraining order.",
    "Buy the dip. Discover it was structural decline. Become a long-term investor.",
    "Past performance is no guarantee of future cope.",
    "Diversification is admitting you have no idea which one is about to explode.",
    "The market rewards patience, conviction, and occasionally being accidentally correct.",
    "Never confuse a bull market with personal growth.",
    "Cash is a position. Unfortunately, so is financial paralysis.",
    "Every bag becomes a long-term investment if you simply refuse to open the app.",
    "The efficient market hypothesis has never met a man with three monitors and a stimulant problem.",
    "Your thesis is strongest immediately before the 38% drawdown.",
    "Compound interest is the eighth wonder of the world. Compound delusion is the ninth.",
    "A falling knife has no handle, but that has never stopped the shareholders.",
    "You don't need to beat the market. You need to stop doing whatever the hell that was.",
    "Volatility is the price of admission. Panic selling is the gift shop.",
    "Markets transfer wealth from the impatient to the patient, and occasionally from everyone to NVIDIA.",
    "Technical analysis is astrology for men who know what VWAP means.",
]

DEFAULT_ATTRIBUTION = "CopeNet"

# Lines CopeNet did not write. Keyed by the quote text so reordering the list above cannot
# silently reassign a byline.
ATTRIBUTED: dict[str, str] = {
    "The market can stay irrational longer than you can stay solvent.": "attributed to Keynes",
    "Price is what you pay. Value is what you get.": "Warren Buffett",
    "Risk comes from not knowing what you're doing.": "Warren Buffett",
}


def quote_for(day: date | None = None) -> dict[str, str] | None:
    """Today's line, or None when the list has been emptied."""
    if not QUOTES:
        return None
    text = QUOTES[(day or date.today()).toordinal() % len(QUOTES)]
    return {"text": text, "attribution": ATTRIBUTED.get(text, DEFAULT_ATTRIBUTION)}
