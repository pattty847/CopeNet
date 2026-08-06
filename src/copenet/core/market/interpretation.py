"""LLM interpretation layer (Insight Engine Phase D) — prompts, schemas, parsing.

Two lanes (operator design, 2026-07-01):
- MARKET READ: one automatic call per interpret run over the whole-market fact packet.
- TICKER READ: on-demand per-asset call from the ticker detail page.

Honesty rails (non-negotiable, enforced in prompt + parsing):
- The model reasons ONLY over the facts in the packet. It may bring general market knowledge and
  genuine opinion, but every claim about THIS data must trace to the packet.
- Statistics (base rates) may only be repeated verbatim from the packet — never invented.
- No forecasts or price targets. Interpretation of evidence, with explicit thesis-killers.
- Output is structured JSON (schema below) and stamped with model id + timestamp in the UI.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Protocol

from copenet.core.model_request import ProviderTextRequest, collect_provider_text
from copenet.prompts import PromptPurpose

MARKET_SYSTEM_PROMPT = """You are the market-interpretation layer of a personal market monitor.
Its owner is a long-term accumulator who checks daily, thinks in weekly candles, and values honest,
evidence-based reads over hype.

You will receive a FACT PACKET of pre-computed, verified market facts (macro, breadth, sector
rotation, pattern flags with calibrated historical base rates, the owner's portfolio, SEC evidence).

Your job: give your genuine interpretation of what this tape is doing — what regime we are in, where
money is rotating, what deserves the owner's attention today, and what would prove the read wrong.
You may use your general market knowledge to contextualize the facts, and you should have opinions.

Hard rules:
- Never invent statistics. Base rates may only be quoted verbatim from the packet.
- No forecasts, no price targets, no "will". Describe weight of evidence, not the future.
- Every attention item must trace to a fact in the packet.
- Each thesis-killer must be concrete and falsifiable ("wrong if X happens").
- If evidence is thin or missing, say so plainly.
- Keep the voice plain and calm. No hype, no emojis.
- When an OVERNIGHT CHANGES section is present, lead with it: the owner reads this at the start of
  the day and cares most about what is DIFFERENT since yesterday. Anchor the headline, summary, and
  attention items on those changes when they are material; if the overnight tape was quiet, say so
  plainly rather than re-describing the standing picture as if it were new.
- When a RECENT SESSIONS section is present, treat this as a continuing story rather than a fresh
  start. The owner reads these in sequence, so hold yourself to your own prior calls: if you have
  said risk-on for three sessions and it still holds, say that; if the tape has broken your call,
  say that outright instead of quietly switching sides. Never re-litigate a past call you cannot
  see in the trail.

Respond with ONLY a JSON object matching exactly this shape (no markdown fences, no commentary):
{
  "headline": "one striking sentence, <= 120 chars",
  "emphasis": "a short substring of headline to visually highlight",
  "summary": "3-5 sentences: your interpretation of the tape, written to be read as prose",
  "regime": "risk-off" | "chop" | "risk-on" | "event-risk",
  "regime_reasoning": "2-4 sentences: why this regime call, citing packet facts",
  "continuity": "2-4 sentences against the RECENT SESSIONS trail: what you called on prior sessions, whether it is holding up, and what specifically changed. Empty string when the packet has no trail.",
  "attention": [ { "symbol": "TICKER", "kind": "short label", "why": "one sentence citing facts" } ],
  "rotation_read": "2-3 sentences on the sector rotation picture, including how it has shifted over the recent sessions",
  "speculative_comment": "1-2 sentences on the speculative lane positions, honest and unhyped",
  "thesis_killers": [ { "signal": "what's being called", "kill": "what would make it wrong" } ],
  "caveats": "1-2 sentences on the limits of this read (data gaps, sample sizes, regime drift)"
}
attention: 2-3 items. thesis_killers: 2-4 items."""

TICKER_SYSTEM_PROMPT = """You are the asset-interpretation layer of a personal market monitor. The
owner is a long-term accumulator (weekly timeframe) who asked for a deeper read on one asset.

You will receive a FACT PACKET of pre-computed, verified facts for that asset: returns, trend
structure, risk state, relative strength, volume, any calibrated pattern flags with historical base
rates, benchmark verdict, SEC evidence, fundamentals (quarterly revenue trend, trailing P/E), recent
web/news search results, and data-quality warnings.

Give your genuine interpretation: what the price action says, the honest bull and bear cases, and
what would change your mind. You may contextualize with general knowledge of the company/sector, but
clearly separate packet facts from your own context.

Hard rules:
- Never invent statistics. Base rates only verbatim from the packet.
- No forecasts, no price targets. Weight of evidence only.
- Respect the DATA QUALITY section — if history is thin, your confidence must say so.
- The owner does not day-trade; frame everything on weekly/positional horizons.
- Plain, calm voice. No hype, no emojis.
- SEPARATE THE HORIZONS: the packet carries both a ~52-week tactical view (RETURNS/TREND/RISK
  STATE) and a multi-year STRUCTURE view (long trend, distance from multi-year high, range
  behavior/consolidation). Anchor "is the trend intact?" on the STRUCTURE horizon; use the tactical
  view for the near-term picture. If they disagree, say so explicitly — that disagreement is often
  the most useful insight.
- In bull_case/bear_case, state plainly which thesis the current structure gives more leeway to,
  and what structural level or behavior would flip that.
- When FUNDAMENTALS/VALUATION are present in the packet, weigh them explicitly — is the growth
  story decelerating or reaccelerating, does the trailing P/E look rich or cheap relative to that
  growth, does it support or undercut the technical picture? If FUNDAMENTALS says "not available,"
  say so rather than guessing at revenue or valuation from general knowledge.
- RECENT WEB/NEWS is a live search snippet, not verified fact — treat headlines as "reportedly"
  context, cross-reference it against the packet's price/fundamentals facts rather than taking it
  at face value, and say so explicitly if the news contradicts what the numbers show. Only cite a
  headline that is actually present in the packet; if it says no results, say news wasn't found —
  never invent a headline from general knowledge of the company.

Respond with ONLY a JSON object matching exactly this shape (no markdown fences, no commentary):
{
  "read": "3-5 sentences: your interpretation of this asset's tape",
  "lean": "bullish" | "bearish" | "neutral",
  "bull_case": "2-3 sentences: the honest case for accumulating here, citing facts",
  "bear_case": "2-3 sentences: the honest case against, citing facts",
  "what_would_change_my_mind": "1-2 concrete, falsifiable conditions",
  "confidence": "low" | "medium" | "high",
  "confidence_reason": "one sentence, tied to data quality and evidence density",
  "key_facts": [ "3-5 short strings, each a packet fact this read leans on" ]
}
"lean" is your honest net directional lean for this asset on the weekly/positional horizon
(the next 1-2 months), given everything in the packet. It is recorded in a forward ledger and
scored against what actually happens — so answer what you actually believe, and use "neutral"
when the evidence genuinely doesn't tilt. This is a lean, not advice or a forecast narrative."""


@dataclass
class MarketRead:
    headline: str
    emphasis: str
    summary: str
    regime: str
    regime_reasoning: str
    # Empty on the first read after archiving shipped, and whenever there is no prior trail.
    continuity: str
    attention: list[dict[str, str]]
    rotation_read: str
    speculative_comment: str
    thesis_killers: list[dict[str, str]]
    caveats: str
    model: str = ""
    generated_at: str = ""

    def to_wire(self) -> dict[str, Any]:
        payload = asdict(self)
        return {_camel(k): v for k, v in payload.items()}


@dataclass
class TickerRead:
    read: str
    bull_case: str
    bear_case: str
    what_would_change_my_mind: str
    confidence: str
    confidence_reason: str
    key_facts: list[str] = field(default_factory=list)
    lean: str = "neutral"  # bullish | bearish | neutral — the scoreable claim for the forward ledger
    model: str = ""
    generated_at: str = ""

    def to_wire(self) -> dict[str, Any]:
        payload = asdict(self)
        return {_camel(k): v for k, v in payload.items()}


def _camel(name: str) -> str:
    parts = name.split("_")
    return parts[0] + "".join(p[:1].upper() + p[1:] for p in parts[1:])


def extract_json(text: str) -> dict[str, Any]:
    """Parse the model's JSON, tolerating markdown fences or stray prose around one object."""
    text = text.strip()
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        parsed = json.loads(fenced.group(1))
        if isinstance(parsed, dict):
            return parsed
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        parsed = json.loads(text[start : end + 1])
        if isinstance(parsed, dict):
            return parsed
    raise ValueError("model response contained no JSON object")


_VALID_REGIMES = {"risk-off", "chop", "risk-on", "event-risk"}
_VALID_CONFIDENCE = {"low", "medium", "high"}
_VALID_LEANS = {"bullish", "bearish", "neutral"}


def parse_market_read(text: str, *, model: str, generated_at: str) -> MarketRead:
    raw = extract_json(text)
    regime = str(raw.get("regime", "chop")).lower().strip()
    attention = [
        {"symbol": str(a.get("symbol", "")).upper(), "kind": str(a.get("kind", "")), "why": str(a.get("why", ""))}
        for a in raw.get("attention", [])
        if isinstance(a, dict)
    ][:3]
    killers = [
        {"signal": str(k.get("signal", "")), "kill": str(k.get("kill", ""))}
        for k in raw.get("thesis_killers", [])
        if isinstance(k, dict)
    ][:4]
    return MarketRead(
        headline=str(raw.get("headline", "")).strip()[:160],
        emphasis=str(raw.get("emphasis", "")).strip(),
        summary=str(raw.get("summary", "")).strip(),
        regime=regime if regime in _VALID_REGIMES else "chop",
        regime_reasoning=str(raw.get("regime_reasoning", "")).strip(),
        continuity=str(raw.get("continuity", "")).strip(),
        attention=attention,
        rotation_read=str(raw.get("rotation_read", "")).strip(),
        speculative_comment=str(raw.get("speculative_comment", "")).strip(),
        thesis_killers=killers,
        caveats=str(raw.get("caveats", "")).strip(),
        model=model,
        generated_at=generated_at,
    )


class _ProviderLike(Protocol):
    def run(self, **kwargs: Any) -> Any: ...


async def _provider_text(provider: _ProviderLike, *, prompt: str, model: str, system_prompt: str) -> str:
    """One-shot provider call (no session) — the proven optimizer/meme-ideation pattern."""
    return await collect_provider_text(
        provider=provider,  # type: ignore[arg-type]
        request=ProviderTextRequest(
            purpose=PromptPurpose.SPECIALIZED,
            phase="market_interpretation",
            prompt=prompt,
            model=model,
            system_prompt=system_prompt,
        ),
    )


async def generate_market_read(
    provider: _ProviderLike, packet: str, *, model: str, generated_at: str
) -> MarketRead:
    text = await _provider_text(
        provider,
        prompt=f"FACT PACKET:\n{packet}",
        model=model,
        system_prompt=MARKET_SYSTEM_PROMPT,
    )
    return parse_market_read(text, model=model, generated_at=generated_at)


async def generate_ticker_read(
    provider: _ProviderLike, packet: str, *, model: str, generated_at: str
) -> TickerRead:
    text = await _provider_text(
        provider,
        prompt=f"FACT PACKET:\n{packet}",
        model=model,
        system_prompt=TICKER_SYSTEM_PROMPT,
    )
    return parse_ticker_read(text, model=model, generated_at=generated_at)


def parse_ticker_read(text: str, *, model: str, generated_at: str) -> TickerRead:
    raw = extract_json(text)
    confidence = str(raw.get("confidence", "low")).lower().strip()
    lean = str(raw.get("lean", "neutral")).lower().strip()
    key_facts = [str(f) for f in raw.get("key_facts", []) if isinstance(f, (str, int, float))][:6]
    return TickerRead(
        read=str(raw.get("read", "")).strip(),
        bull_case=str(raw.get("bull_case", "")).strip(),
        bear_case=str(raw.get("bear_case", "")).strip(),
        what_would_change_my_mind=str(raw.get("what_would_change_my_mind", "")).strip(),
        confidence=confidence if confidence in _VALID_CONFIDENCE else "low",
        confidence_reason=str(raw.get("confidence_reason", "")).strip(),
        key_facts=key_facts,
        lean=lean if lean in _VALID_LEANS else "neutral",
        model=model,
        generated_at=generated_at,
    )
