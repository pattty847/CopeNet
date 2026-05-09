from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass

from copenet.providers import Provider


@dataclass(frozen=True)
class PromptOptimizationVariant:
    id: str
    label: str
    prompt: str
    rationale: str

    def to_dict(self) -> dict[str, str]:
        return {
            "id": self.id,
            "label": self.label,
            "prompt": self.prompt,
            "rationale": self.rationale,
        }


@dataclass(frozen=True)
class PromptOptimizationResult:
    variants: list[PromptOptimizationVariant]
    provider: str
    model: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "variants": [variant.to_dict() for variant in self.variants],
            "provider": self.provider,
            "model": self.model,
        }


_FIXED_VARIANTS: tuple[tuple[str, str, str], ...] = (
    (
        "sharper",
        "Sharper",
        "Make the prompt tighter, clearer, and less ambiguous without bloating it.",
    ),
    (
        "more_context",
        "More Context",
        "Add useful context, constraints, and desired output shape while preserving the original request.",
    ),
    (
        "execution_ready",
        "Execution-Ready",
        "Rewrite the prompt so an agent can act on it with clear goals, success criteria, and expected deliverables.",
    ),
)


async def optimize_prompt_variants(
    *,
    provider: Provider,
    prompt: str,
    model: str | None,
    custom_transform: str | None = None,
) -> PromptOptimizationResult:
    resolved_model = await _resolve_model(provider, model)
    requested_variants = list(_FIXED_VARIANTS)
    if custom_transform:
        requested_variants.append(("custom", "Custom Transform", custom_transform.strip()))

    try:
        raw_text = await _run_provider_text(
            provider=provider,
            model=resolved_model,
            system_prompt=_optimizer_system_prompt(),
            prompt=_optimizer_user_prompt(prompt=prompt, requested_variants=requested_variants),
        )
        parsed_variants = _parse_optimizer_response(raw_text, prompt, requested_variants)
    except Exception:
        parsed_variants = _fallback_variants(prompt, requested_variants)

    return PromptOptimizationResult(variants=parsed_variants, provider=provider.name, model=resolved_model)


async def _resolve_model(provider: Provider, requested_model: str | None) -> str:
    if requested_model:
        return requested_model
    models = await provider.list_models()
    for candidate in models:
        if candidate.kind == "chat":
            return candidate.id
    raise ValueError(f"provider {provider.name} has no chat-capable models available")


async def _run_provider_text(*, provider: Provider, prompt: str, model: str, system_prompt: str) -> str:
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


def _optimizer_system_prompt() -> str:
    return (
        "You are a prompt optimization engine for an agent workspace. "
        "Your job is to preserve the user's actual intent while improving clarity, specificity, constraints, and execution-readiness. "
        "Do not change the task. Do not add fake requirements. Do not use marketing fluff. "
        "Return strict JSON only with this shape: "
        '{"variants":[{"id":"sharper","label":"Sharper","prompt":"...","rationale":"..."}]}. '
        "No markdown fences. No commentary outside the JSON."
    )


def _optimizer_user_prompt(*, prompt: str, requested_variants: list[tuple[str, str, str]]) -> str:
    lines = [
        "Original prompt:",
        prompt.strip(),
        "",
        "Return one optimized variant for each requested id below.",
        "Each rationale should be one short sentence.",
        "",
        "Requested variants:",
    ]
    for variant_id, label, instruction in requested_variants:
        lines.append(f"- id={variant_id} | label={label} | transform={instruction}")
    lines.extend(
        [
            "",
            "Rules:",
            "- Preserve the user's voice and goal.",
            "- Make missing deliverables explicit when helpful.",
            "- Keep prompts practical, not corporate.",
            "- Return all requested variants in the same order.",
        ]
    )
    return "\n".join(lines)


def _parse_optimizer_response(
    raw_text: str,
    original_prompt: str,
    requested_variants: list[tuple[str, str, str]],
) -> list[PromptOptimizationVariant]:
    payload = json.loads(_extract_json(raw_text))
    raw_variants = payload.get("variants")
    if not isinstance(raw_variants, list):
        raise ValueError("optimizer response missing variants array")

    by_id: dict[str, PromptOptimizationVariant] = {}
    for raw_variant in raw_variants:
        if not isinstance(raw_variant, dict):
            continue
        variant_id = str(raw_variant.get("id") or "").strip().lower()
        label = str(raw_variant.get("label") or "").strip()
        prompt = str(raw_variant.get("prompt") or "").strip()
        rationale = str(raw_variant.get("rationale") or "").strip()
        if not variant_id or not prompt:
            continue
        by_id[variant_id] = PromptOptimizationVariant(
            id=variant_id,
            label=label or variant_id.replace("_", " ").title(),
            prompt=prompt,
            rationale=rationale or "Clarified the request while preserving intent.",
        )

    variants: list[PromptOptimizationVariant] = []
    for variant_id, label, instruction in requested_variants:
        variant = by_id.get(variant_id)
        variants.append(
            variant or _fallback_variant(
                prompt=original_prompt,
                original_prompt=original_prompt,
                variant_id=variant_id,
                label=label,
                instruction=instruction,
            )
        )

    if any(not variant.prompt for variant in variants):
        raise ValueError("optimizer returned empty prompt text")
    return variants


def _extract_json(raw_text: str) -> str:
    text = raw_text.strip()
    if text.startswith("```"):
        match = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return text


def _fallback_variants(
    original_prompt: str,
    requested_variants: list[tuple[str, str, str]],
) -> list[PromptOptimizationVariant]:
    return [
        _fallback_variant(prompt=original_prompt, original_prompt=original_prompt, variant_id=variant_id, label=label, instruction=instruction)
        for variant_id, label, instruction in requested_variants
    ]


def _fallback_variant(
    *,
    prompt: str,
    original_prompt: str | None,
    variant_id: str,
    label: str,
    instruction: str,
) -> PromptOptimizationVariant:
    base_prompt = (original_prompt or prompt or "").strip()
    if variant_id == "sharper":
        optimized = (
            f"Task: {base_prompt}\n\n"
            "Please answer directly, remove ambiguity, and keep the response concise but specific."
        )
        rationale = "Tightened the wording and made the ask more explicit."
    elif variant_id == "more_context":
        optimized = (
            f"Help me with this request: {base_prompt}\n\n"
            "Please clarify the goal, include useful constraints or assumptions, and structure the response so the result is easy to act on."
        )
        rationale = "Added context and output-shape guidance without changing the goal."
    elif variant_id == "execution_ready":
        optimized = (
            f"Execute or design the following task: {base_prompt}\n\n"
            "Please define the objective, assumptions, concrete steps, expected deliverable, and how success should be judged."
        )
        rationale = "Reframed the prompt so an agent can act on it cleanly."
    else:
        optimized = (
            f"Original request: {base_prompt}\n\n"
            f"Transform request: {instruction}\n\n"
            "Rewrite the response accordingly while preserving the user's intent."
        )
        rationale = "Applied the requested custom transform while keeping the original intent visible."
    return PromptOptimizationVariant(id=variant_id, label=label, prompt=optimized.strip(), rationale=rationale)
