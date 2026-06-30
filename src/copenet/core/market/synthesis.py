"""Facts-only market briefing synthesis."""

from __future__ import annotations

from .models import Briefing, ContrarianNote, EvidenceItem, MacroItem


def synthesize_briefing(*, macro: list[MacroItem], evidence: list[EvidenceItem], breadth_pct: float) -> tuple[Briefing, list[ContrarianNote]]:
    vix = _macro_value(macro, "VIX")
    risk_tone = "risk-on" if breadth_pct >= 55 and vix < 20 else "risk-off" if breadth_pct < 40 or vix >= 25 else "chop"
    headline = f"{risk_tone.title()} tape, with breadth at {breadth_pct:.0f}%."
    summary = (
        f"Computed facts show VIX at {vix:.1f} and {len(evidence)} recent SEC evidence item(s). "
        "This is an orientation read, not a forecast."
    )
    changed = [{"text": f"breadth -> {breadth_pct:.0f}%", "tone": "up" if breadth_pct >= 50 else "down"}]
    attention = []
    for item in evidence[:3]:
        attention.append({"kind": item.type, "label": item.headline[:80], "glyph": "SEC", "symbol": item.symbol})
    briefing = Briefing(
        headline=headline,
        emphasis=f"{breadth_pct:.0f}%",
        summary=summary,
        changed=changed,
        attention=attention,  # type: ignore[arg-type]
        vix=vix,
        breadth_pct=breadth_pct,
    )
    contrarian = [
        ContrarianNote(signal="Market breadth", kill="The read weakens if fewer than 40% of tracked names hold above weekly trend."),
        ContrarianNote(signal="Volatility", kill="The read changes if VIX expands above 25 while indexes fail to make higher highs."),
        ContrarianNote(signal="SEC evidence", kill="Treat filing/insider color as context only unless price and benchmark-relative data confirm it."),
    ]
    return briefing, contrarian


def _macro_value(items: list[MacroItem], label: str) -> float:
    for item in items:
        if item.label == label:
            try:
                return float(item.value.replace("$", "").replace(",", ""))
            except ValueError:
                return 0.0
    return 0.0
