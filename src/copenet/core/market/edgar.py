"""Thin CopeTech-Edgar adapter for Market Monitor evidence."""

from __future__ import annotations

from typing import Any

from .models import ChartEvent, EvidenceItem

SEC_API_USER_AGENT = "Patrick McDermott (CopeNet) pattty847@gmail.com"


def fetch_evidence(symbols: list[str], *, limit_per_symbol: int = 2) -> list[EvidenceItem]:
    try:
        from copetech_sec import SECDataFetcher
    except ImportError:
        return []
    evidence: list[EvidenceItem] = []
    fetcher = SECDataFetcher(user_agent=SEC_API_USER_AGENT)
    for symbol in symbols:
        evidence.extend(_evidence_for_symbol(fetcher, symbol, limit=limit_per_symbol))
    return evidence


def chart_events_from_evidence(evidence: list[EvidenceItem]) -> list[ChartEvent]:
    # CopeTech payload dates vary by endpoint; preserve contract with evidence
    # panel first, then add dated markers when the wrapper exposes them.
    return []


def _evidence_for_symbol(fetcher: Any, symbol: str, *, limit: int) -> list[EvidenceItem]:
    rows: list[EvidenceItem] = []
    try:
        payload = fetcher.get_insider_signal_payload(symbol)
    except Exception:
        payload = None
    for item in _coerce_rows(payload)[:limit]:
        headline = str(item.get("headline") or item.get("summary") or item.get("title") or "Insider activity").strip()
        rows.append(EvidenceItem(type="Insider", symbol=symbol, headline=headline, source="SEC", tone="flat", url=_url(item)))
    try:
        filings = fetcher.get_company_filings(symbol, form_type="8-K", limit=limit)
    except Exception:
        filings = None
    for item in _coerce_rows(filings)[:limit]:
        headline = str(item.get("headline") or item.get("description") or item.get("form") or "8-K filing").strip()
        rows.append(EvidenceItem(type="8-K", symbol=symbol, headline=headline, source="SEC", tone="flat", url=_url(item)))
    return rows


def _coerce_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("items", "signals", "filings", "data", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return [payload]
    return []


def _url(item: dict[str, Any]) -> str | None:
    value = item.get("url") or item.get("link") or item.get("filing_url")
    text = str(value).strip() if value else ""
    return text or None
