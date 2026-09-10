"""Format benchmark, SEC and news evidence with explicit missing-data text."""

from urllib.parse import urlparse


def _domain(url: str) -> str:
    try:
        return urlparse(url).hostname or url
    except ValueError:
        return url


def _fmt_money(value: float) -> str:
    magnitude = abs(value)
    if magnitude >= 1e9:
        return f"${value / 1e9:.2f}B"
    if magnitude >= 1e6:
        return f"${value / 1e6:.1f}M"
    return f"${value:,.0f}"


def benchmark_sections(verdict: list[dict] | None) -> list[str]:
    sections: list[str] = []
    if verdict:
        rows = []
        for v in verdict:
            excess = v.get("excess_return_pct")
            asset_return = v.get("asset_return_pct")
            benchmark_return = v.get("benchmark_return_pct")
            beta = v.get("beta")
            beta_adjusted = v.get("beta_adjusted_excess_pct")
            rows.append(
                f"vs {v['bench']}: {v['label']} by {excess:+.1f}% raw "
                f"(asset {asset_return:+.1f}%, benchmark {benchmark_return:+.1f}%; "
                f"beta {beta:.2f}, beta-adjusted residual {beta_adjusted:+.1f}%)"
                if None not in (excess, asset_return, benchmark_return, beta, beta_adjusted)
                else f"vs {v['bench']}: insufficient overlapping history"
            )
        sections.append("BENCHMARK CHECK (trailing 52w; verdict uses raw excess return): " + "; ".join(rows))

    return sections


def evidence_sections(evidence: list[dict] | None) -> list[str]:
    sections: list[str] = []
    if evidence:
        rows = [f"[{e['type']}] {e['headline']} ({e.get('source', '')})" for e in evidence[:5]]
        sections.append("EVIDENCE: " + "; ".join(rows))

    return sections


def fundamentals_sections(fundamentals: dict | None) -> list[str]:
    sections: list[str] = []
    if fundamentals:
        revenue_q = fundamentals.get("revenueQuarterly") or []
        if revenue_q:
            rows = []
            for r in revenue_q[:4]:
                yoy = r.get("yoy_pct")
                yoy_txt = f", YoY {yoy:+.1%}" if yoy is not None else ""
                rows.append(f"{r['period']} {_fmt_money(r['value'])}{yoy_txt}")
            sections.append("FUNDAMENTALS — REVENUE (quarterly, newest first): " + "; ".join(rows))
        pe_ttm = fundamentals.get("peTtm")
        eps_ttm = fundamentals.get("epsTtm")
        if pe_ttm is not None:
            sections.append(f"VALUATION: trailing P/E ~{pe_ttm:.1f}x (TTM EPS ${eps_ttm:.2f})")
        elif eps_ttm is not None and eps_ttm <= 0:
            sections.append("VALUATION: trailing EPS is non-positive — P/E not meaningful")
        if not revenue_q and eps_ttm is None:
            sections.append("FUNDAMENTALS: SEC data found but no usable revenue/EPS series for this filer.")
    else:
        sections.append("FUNDAMENTALS: not available (ETF, or no matching SEC company facts).")

    return sections


def news_sections(news: list[dict] | None, news_source: str | None) -> list[str]:
    sections: list[str] = []
    if news:
        rows = [
            f'"{n["title"]}" ({_domain(n["url"])}): {n.get("snippet", "").strip()[:180]}' for n in news[:5]
        ]
        source_note = f" [{news_source}]" if news_source else ""
        sections.append(f"RECENT WEB/NEWS{source_note}: " + " | ".join(rows))
    else:
        sections.append(
            "RECENT WEB/NEWS: no results returned (or search unavailable) — do not invent headlines."
        )

    return sections
