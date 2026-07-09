"""Thin CopeTech-Edgar adapter for Market Monitor evidence."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .models import ChartEvent, EvidenceItem, TickerEvidencePayload, Tone

SEC_API_USER_AGENT = "Patrick McDermott (CopeNet) pattty847@gmail.com"
TICKER_FORM4_EVENT_LIMIT = 20
TICKER_FORM4_FILING_LIMIT = 40
TICKER_8K_EVENT_LIMIT = 5
TICKER_144_RECORD_LIMIT = 5
TICKER_144_FILING_LIMIT = 25
TICKER_CLUSTER_LIMIT = 2
TICKER_SEC_DAYS_BACK = 180
FORM_144_DAYS_BACK = 90


async def fetch_evidence(symbols: list[str], *, limit_per_symbol: int = 2) -> list[EvidenceItem]:
    fetcher_cls = _sec_fetcher_class()
    if fetcher_cls is None:
        return []
    evidence: list[EvidenceItem] = []
    fetcher = fetcher_cls(user_agent=SEC_API_USER_AGENT)
    for symbol in symbols:
        evidence.extend(await _evidence_for_symbol(fetcher, symbol, limit=limit_per_symbol))
    return evidence


async def fetch_ticker_evidence(symbol: str, *, refresh: bool = False) -> TickerEvidencePayload:
    normalized = symbol.strip().upper()
    fetcher_cls = _sec_fetcher_class()
    if fetcher_cls is None:
        return TickerEvidencePayload(symbol=normalized, evidence=[], events=[], as_of=_now_iso(), refreshed=refresh)
    fetcher = fetcher_cls(user_agent=SEC_API_USER_AGENT)
    evidence: list[EvidenceItem] = []
    insider_payload = await _fetch_insider_payload(fetcher, normalized, refresh=refresh)
    for cluster in _clusters_from_payload(insider_payload)[:TICKER_CLUSTER_LIMIT]:
        evidence.append(_cluster_evidence(normalized, cluster))
    for event in _events_from_payload(insider_payload)[:TICKER_FORM4_EVENT_LIMIT]:
        evidence.append(_insider_evidence(normalized, event))
    form144_payload = await _fetch_144_payload(fetcher, normalized, refresh=refresh)
    for record in _records_from_payload(form144_payload)[:TICKER_144_RECORD_LIMIT]:
        evidence.append(_planned_sale_evidence(normalized, record))
    form8k_payload = await _fetch_8k_payload(fetcher, normalized, refresh=refresh)
    for event in _events_from_payload(form8k_payload)[:TICKER_8K_EVENT_LIMIT]:
        evidence.append(_form8k_evidence(normalized, event))
    return TickerEvidencePayload(
        symbol=normalized,
        evidence=evidence,
        events=chart_events_from_evidence(evidence),
        as_of=_payload_as_of(insider_payload, form8k_payload, form144_payload) or _now_iso(),
        refreshed=refresh,
    )


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


_CHART_KIND_BY_TYPE = {"Insider": "insider", "8-K": "8-K", "Form 144": "planned-sale"}


def chart_events_from_evidence(evidence: list[EvidenceItem]) -> list[ChartEvent]:
    events: list[ChartEvent] = []
    for item in evidence:
        if item.t is None:
            continue
        kind = _CHART_KIND_BY_TYPE.get(item.type)
        if kind is None:
            continue
        events.append(ChartEvent(t=item.t, kind=kind, glyph=_glyph(item)))  # type: ignore[arg-type]
    return events


def _sec_fetcher_class() -> Any | None:
    try:
        from copetech_sec import SECDataFetcher
    except ImportError:
        return None
    return SECDataFetcher


def _glyph(item: EvidenceItem) -> str:
    if item.type == "Insider":
        if item.tone == "up":
            return "▲"
        if item.tone == "down":
            return "▼"
        return "●"
    if item.type == "Form 144":
        return "▽"
    return "8-K"


async def _evidence_for_symbol(fetcher: Any, symbol: str, *, limit: int) -> list[EvidenceItem]:
    rows: list[EvidenceItem] = []
    try:
        payload = await fetcher.get_insider_signal_payload(symbol)
    except Exception:
        payload = None
    for cluster in _clusters_from_payload(payload)[:1]:
        rows.append(_cluster_evidence(symbol, cluster))
    for event in _events_from_payload(payload)[:limit]:
        rows.append(_insider_evidence(symbol, event))
    try:
        form144 = await fetcher.get_planned_insider_sales(symbol, days_back=FORM_144_DAYS_BACK, filing_limit=TICKER_144_FILING_LIMIT)
    except Exception:
        form144 = None
    for record in _records_from_payload(form144)[:1]:
        rows.append(_planned_sale_evidence(symbol, record))
    try:
        filings = await fetcher.get_8k_events(symbol)
    except Exception:
        filings = None
    # Dashboard panel: high-signal 8-Ks only (exec changes, results, M&A, distress,
    # restructuring, material agreements) — routine exhibits/disclosure stay per-ticker.
    high_signal = [event for event in _events_from_payload(filings) if event.get("high_signal")]
    for event in high_signal[:limit]:
        rows.append(_form8k_evidence(symbol, event))
    return rows


async def _fetch_insider_payload(fetcher: Any, symbol: str, *, refresh: bool) -> Any:
    try:
        if refresh:
            return await fetcher.refresh_insider_signal_payload(
                symbol,
                days_back=TICKER_SEC_DAYS_BACK,
                filing_limit=TICKER_FORM4_FILING_LIMIT,
            )
        return await fetcher.get_insider_signal_payload(
            symbol,
            days_back=TICKER_SEC_DAYS_BACK,
            filing_limit=TICKER_FORM4_FILING_LIMIT,
        )
    except Exception:
        return None


async def _fetch_8k_payload(fetcher: Any, symbol: str, *, refresh: bool) -> Any:
    try:
        if refresh:
            return await fetcher.refresh_8k_events(
                symbol,
                days_back=TICKER_SEC_DAYS_BACK,
                filing_limit=TICKER_8K_EVENT_LIMIT,
            )
        return await fetcher.get_8k_events(
            symbol,
            days_back=TICKER_SEC_DAYS_BACK,
            filing_limit=TICKER_8K_EVENT_LIMIT,
        )
    except Exception:
        return None


async def _fetch_144_payload(fetcher: Any, symbol: str, *, refresh: bool) -> Any:
    """Form 144 has no incremental refresh path (records are light) — refresh just bypasses
    the daily cache for a full refetch."""
    try:
        return await fetcher.get_planned_insider_sales(
            symbol,
            days_back=FORM_144_DAYS_BACK,
            filing_limit=TICKER_144_FILING_LIMIT,
            use_cache=not refresh,
        )
    except Exception:
        return None


def _events_from_payload(payload: Any) -> list[dict[str, Any]]:
    return _dict_rows(payload, "events")


def _clusters_from_payload(payload: Any) -> list[dict[str, Any]]:
    return _dict_rows(payload, "clusters")


def _records_from_payload(payload: Any) -> list[dict[str, Any]]:
    return _dict_rows(payload, "records")


def _dict_rows(payload: Any, key: str) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        rows = payload.get(key)
        if isinstance(rows, list):
            return [item for item in rows if isinstance(item, dict)]
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
        flag="high-signal" if event.get("high_signal") else None,
    )


def _cluster_evidence(symbol: str, cluster: dict[str, Any]) -> EvidenceItem:
    """One evidence row for a multi-insider buy window — the anomaly itself, not any single Form 4."""
    insiders = cluster.get("unique_insiders") or 0
    total_value = cluster.get("total_value")
    window = _format_window(cluster.get("window_start"), cluster.get("window_end"))
    value_text = f" ~{_fmt_value(float(total_value))}" if isinstance(total_value, (int, float)) and total_value else ""
    urls = cluster.get("filing_urls")
    return EvidenceItem(
        type="Insider",
        symbol=symbol,
        headline=f"Cluster buy — {insiders} insiders{value_text}{window}",
        source="SEC Form 4",
        tone="up",
        url=urls[0] if isinstance(urls, list) and urls else None,
        t=_to_unix(cluster.get("window_end") or cluster.get("window_start")),
        flag="cluster",
    )


def _planned_sale_evidence(symbol: str, record: dict[str, Any]) -> EvidenceItem:
    """Form 144: an insider FILING INTENT to sell — forward-looking, unlike Form 4's executed trades."""
    who = str(record.get("account_name") or record.get("signer") or "Insider").strip()
    shares = record.get("planned_shares")
    value = record.get("aggregate_market_value")
    share_text = f" {int(shares):,} shares" if isinstance(shares, (int, float)) and shares else ""
    value_text = f" (~{_fmt_value(float(value))})" if isinstance(value, (int, float)) and value else ""
    # The sale can be scheduled ahead of the filing — surface the intended date when it differs.
    approx = str(record.get("approx_sale_date") or "").strip()
    signature = str(record.get("signature_date") or "").strip()
    sale_text = f" · sale ~{approx}" if approx and approx != signature else ""
    return EvidenceItem(
        type="Form 144",
        symbol=symbol,
        headline=f"{who} filed to sell{share_text}{value_text}{sale_text}".strip(),
        source="SEC Form 144",
        tone="down",
        url=record.get("form_url"),
        t=_to_unix(record.get("signature_date") or record.get("filing_date")),
    )


def _fmt_value(value: float) -> str:
    magnitude = abs(value)
    if magnitude >= 1e9:
        return f"${value / 1e9:.2f}B"
    if magnitude >= 1e6:
        return f"${value / 1e6:.1f}M"
    if magnitude >= 1e3:
        return f"${value / 1e3:.0f}K"
    return f"${value:,.0f}"


def _format_window(start: Any, end: Any) -> str:
    if isinstance(start, str) and isinstance(end, str) and start and end:
        return f" ({start} → {end})" if start != end else f" ({start})"
    return ""


def _to_unix(date_str: Any) -> int | None:
    if not date_str or not isinstance(date_str, str):
        return None
    try:
        parsed = datetime.strptime(date_str[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        return int(parsed.timestamp())
    except ValueError:
        return None


def _payload_as_of(*payloads: Any) -> str | None:
    values: list[str] = []
    for payload in payloads:
        if isinstance(payload, dict) and isinstance(payload.get("as_of"), str):
            values.append(payload["as_of"])
    return max(values) if values else None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
