"""Compose one ticker fact packet from explicit, ordered evidence sections."""

from typing import Any
from .features import FeatureSet
from .base_rates import BaseRate
from .ticker_technical_sections import (
    quality_sections,
    return_sections,
    trend_sections,
    structure_sections,
    risk_sections,
    relative_sections,
    volume_sections,
    pattern_sections,
)
from .ticker_evidence_sections import (
    benchmark_sections,
    evidence_sections,
    fundamentals_sections,
    news_sections,
)


def ticker_fact_packet(
    fs: FeatureSet,
    *,
    name: str,
    base_rate: BaseRate | None,
    verdict: list[dict[str, Any]] | None = None,
    evidence: list[dict[str, Any]] | None = None,
    fundamentals: dict[str, Any] | None = None,
    news: list[dict[str, Any]] | None = None,
    news_source: str | None = None,
) -> str:
    """Format a single asset's packet from its typed FeatureSet."""
    sections = [f"ASSET: {fs.symbol} ({name}) · weekly timeframe · basis {fs.basis}"]
    sections.extend(quality_sections(fs))
    sections.extend(return_sections(fs))
    sections.extend(trend_sections(fs))
    sections.extend(structure_sections(fs))
    sections.extend(risk_sections(fs))
    sections.extend(relative_sections(fs))
    sections.extend(volume_sections(fs))
    sections.extend(pattern_sections(fs, base_rate))
    sections.extend(benchmark_sections(verdict))
    sections.extend(evidence_sections(evidence))
    sections.extend(fundamentals_sections(fundamentals))
    sections.extend(news_sections(news, news_source))
    return "\n".join(sections)
