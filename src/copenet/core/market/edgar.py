"""Thin CopeTech-Edgar adapter for Market Monitor evidence."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .models import ChartEvent, EvidenceItem, Tone

SEC_API_USER_AGENT = "Patrick McDermott (CopeNet) pattty847@gmail.com"


async def fetch_evidence(symbols: list[str], *, limit_per_symbol: int = 2) -> list[EvidenceItem]:
    try:
        from copetech_sec import SECDataFetcher
    except ImportError:
        return []
    evidence: list[EvidenceItem] = []
    fetcher = SECDataFetcher(user_agent=SEC_API_USER_AGENT)
    for symbol in symbols:
        evidence.extend(await _evidence_for_symbol(fetcher, symbol, limit=limit_per_symbol))
    return evidence


async def fetch_fundamentals(symbol: str, *, periods: int = 8) -> dict[str, Any] | None:
    """Quarterly revenue + EPS history from CopeTech-Edgar's XBRL parser, for the model's fact
    packet. Returns None for symbols with no company facts (ETFs, banks with no matching revenue
    tag, etc.) rather than a hollow dict — callers should treat that as "unavailable", not "zero"."""
    try:
        from copetech_sec import SECDataFetcher
    except ImportError:
        return None
    fetcher = SECDataFetcher(user_agent=SEC_API_USER_AGENT)
    try:
        trend = await fetcher.get_financial_trend(symbol, periods=periods)
    except Exception:
        return None
    if not trend:
        return None
    metrics = trend.get("metrics") or {}
    revenue = (metrics.get("revenue") or {}).get("quarterly") or []
    eps = (metrics.get("eps") or {}).get("quarterly") or []
    if not revenue and not eps:
        return None
    return {
        "entityName": trend.get("entityName"),
        "sourceForm": trend.get("source_form"),
        "periodEnd": trend.get("period_end"),
        "revenueQuarterly": revenue,
        "epsQuarterly": eps,
    }


def chart_events_from_evidence(evidence: list[EvidenceItem]) -> list[ChartEvent]:
    events: list[ChartEvent] = []
    for item in evidence:
        if item.t is None:
            continue
        kind: Any = "insider" if item.type == "Insider" else "8-K"
        if item.type not in ("Insider", "8-K"):
            continue
        glyph = _glyph(item)
        events.append(ChartEvent(t=item.t, kind=kind, glyph=glyph))
    return events


def _glyph(item: EvidenceItem) -> str:
    if item.type == "Insider":
        if item.tone == "up":
            return "▲"
        if item.tone == "down":
            return "▼"
        return "●"
    return "8-K"


async def _evidence_for_symbol(fetcher: Any, symbol: str, *, limit: int) -> list[EvidenceItem]:
    rows: list[EvidenceItem] = []
    try:
        payload = await fetcher.get_insider_signal_payload(symbol)
    except Exception:
        payload = None
    for event in _events_from_payload(payload)[:limit]:
        rows.append(_insider_evidence(symbol, event))
    try:
        filings = await fetcher.get_8k_events(symbol)
    except Exception:
        filings = None
    for event in _events_from_payload(filings)[:limit]:
        rows.append(_form8k_evidence(symbol, event))
    return rows


def _events_from_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        events = payload.get("events")
        if isinstance(events, list):
            return [item for item in events if isinstance(item, dict)]
    return []


def _insider_evidence(symbol: str, event: dict[str, Any]) -> EvidenceItem:
    owner = str(event.get("owner_name") or "Insider").strip()
    role = str(event.get("owner_role") or "").strip()
    shares = event.get("shares")
    tone: Tone = "flat"
    if event.get("is_acquisition"):
        tone = "up"
        action = "bought"
    elif event.get("is_disposition"):
        tone = "down"
        action = "sold"
    else:
        action = "transacted"
    who = f"{owner} ({role})" if role else owner
    share_text = f" {int(shares):,} shares" if isinstance(shares, (int, float)) and shares else ""
    headline = f"{who} {action}{share_text}".strip()
    return EvidenceItem(
        type="Insider",
        symbol=symbol,
        headline=headline,
        source="SEC Form 4",
        tone=tone,
        url=event.get("form_url"),
        t=_to_unix(event.get("transaction_date") or event.get("filing_date")),
    )


def _form8k_evidence(symbol: str, event: dict[str, Any]) -> EvidenceItem:
    items = event.get("items")
    labels = [str(item.get("label")) for item in items if isinstance(item, dict) and item.get("label")] if isinstance(items, list) else []
    headline = ", ".join(labels) if labels else "8-K filing"
    return EvidenceItem(
        type="8-K",
        symbol=symbol,
        headline=headline,
        source="SEC 8-K",
        tone="flat",
        url=event.get("url"),
        t=_to_unix(event.get("filing_date") or event.get("report_date")),
    )


def _to_unix(date_str: Any) -> int | None:
    if not date_str or not isinstance(date_str, str):
        return None
    try:
        parsed = datetime.strptime(date_str[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        return int(parsed.timestamp())
    except ValueError:
        return None
