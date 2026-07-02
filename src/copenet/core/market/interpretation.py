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

import asyncio
import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Protocol

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

Respond with ONLY a JSON object matching exactly this shape (no markdown fences, no commentary):
{
  "headline": "one striking sentence, <= 120 chars",
  "emphasis": "a short substring of headline to visually highlight",
  "summary": "2-3 sentences: your interpretation of the tape",
  "regime": "risk-off" | "chop" | "risk-on" | "event-risk",
  "regime_reasoning": "1-2 sentences: why this regime call, citing packet facts",
  "attention": [ { "symbol": "TICKER", "kind": "short label", "why": "one sentence citing facts" } ],
  "rotation_read": "1-2 sentences on the sector rotation picture",
  "speculative_comment": "1-2 sentences on the speculative lane positions, honest and unhyped",
  "thesis_killers": [ { "signal": "what's being called", "kill": "what would make it wrong" } ],
  "caveats": "1-2 sentences on the limits of this read (data gaps, sample sizes, regime drift)"
}
attention: 2-3 items. thesis_killers: 2-4 items."""

TICKER_SYSTEM_PROMPT = """You are the asset-interpretation layer of a personal market monitor. The
owner is a long-term accumulator (weekly timeframe) who asked for a deeper read on one asset.

You will receive a FACT PACKET of pre-computed, verified facts for that asset: returns, trend
structure, risk state, relative strength, volume, any calibrated pattern flags with historical base
rates, benchmark verdict, SEC evidence, and data-quality warnings.

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

Respond with ONLY a JSON object matching exactly this shape (no markdown fences, no commentary):
{
  "read": "3-5 sentences: your interpretation of this asset's tape",
  "bull_case": "2-3 sentences: the honest case for accumulating here, citing facts",
  "bear_case": "2-3 sentences: the honest case against, citing facts",
  "what_would_change_my_mind": "1-2 concrete, falsifiable conditions",
  "confidence": "low" | "medium" | "high",
  "confidence_reason": "one sentence, tied to data quality and evidence density",
  "key_facts": [ "3-5 short strings, each a packet fact this read leans on" ]
}"""


@dataclass
class MarketRead:
    headline: str
    emphasis: str
    summary: str
    regime: str
    regime_reasoning: str
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
    abort_event = asyncio.Event()
    chunks: list[str] = []
    async for event in provider.run(
        prompt=prompt,
        provider_session_id=None,
        abort_event=abort_event,
        model=model,
        system_prompt=system_prompt,
    ):
        if event.kind == "delta" and event.text:
            chunks.append(event.text)
        elif event.kind == "final" and event.text:
            chunks.append(event.text)
    return "".join(chunks).strip()


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
    key_facts = [str(f) for f in raw.get("key_facts", []) if isinstance(f, (str, int, float))][:6]
    return TickerRead(
        read=str(raw.get("read", "")).strip(),
        bull_case=str(raw.get("bull_case", "")).strip(),
        bear_case=str(raw.get("bear_case", "")).strip(),
        what_would_change_my_mind=str(raw.get("what_would_change_my_mind", "")).strip(),
        confidence=confidence if confidence in _VALID_CONFIDENCE else "low",
        confidence_reason=str(raw.get("confidence_reason", "")).strip(),
        key_facts=key_facts,
        model=model,
        generated_at=generated_at,
    )
