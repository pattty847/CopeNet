"""Provider orchestration for meme ideation and refinement."""

from __future__ import annotations

import asyncio

from copenet.core.meme_knowledge import build_meme_knowledge_index, build_meme_knowledge_pack
from copenet.providers.base import Provider

from .meme_ideation_constants import (
    MEME_IDEATION_PROMPT_VERSION,
    MEME_IDEATION_SCHEMA_VERSION,
    _LOCAL_PROVIDER_IDS,
    _MAX_REQUESTED_COUNT,
)
from .meme_ideation_models import MemeIdeationRequest, MemeIdeationResponse, MemeRefinementRequest, MemeRefinementResponse
from .meme_ideation_parsing import parse_meme_ideation_output, parse_meme_refinement_output
from .meme_ideation_prompts import (
    build_meme_refinement_system_prompt,
    build_meme_refinement_user_prompt,
    build_meme_system_prompt,
    build_meme_user_prompt,
    build_mutation_plan,
)
from .meme_ideation_scoring import _judge_candidates


async def _resolve_model(provider: Provider, requested_model: str | None) -> str:
    if requested_model:
        return requested_model
    models = await provider.list_models()
    for model in models:
        if model.kind == "chat":
            return model.id
    raise ValueError("provider has no chat-capable models available")


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
    return "".join(chunks).strip()


async def ideate_memes(
    *,
    provider_name: str,
    provider: Provider,
    request: MemeIdeationRequest,
) -> MemeIdeationResponse:
    if provider_name not in _LOCAL_PROVIDER_IDS:
        raise ValueError(f"provider {provider_name} is not a supported local meme ideation provider")

    knowledge_context = build_meme_knowledge_index()
    knowledge_pack = build_meme_knowledge_pack(
        knowledge_context,
        topic=request.topic,
        trend_summary=request.trend_summary,
        image_springboard=request.image_springboard,
        tone_hints=request.tone_hints,
    )
    mutation_plan = build_mutation_plan(request, knowledge_pack)
    system_prompt = build_meme_system_prompt(request, knowledge_pack=knowledge_pack, mutation_plan=mutation_plan)
    user_prompt = build_meme_user_prompt(request, knowledge_pack=knowledge_pack, mutation_plan=mutation_plan)
    resolved_model = await _resolve_model(provider, request.model)

    raw_text = await _run_provider_text(provider=provider, prompt=user_prompt, model=resolved_model, system_prompt=system_prompt)
    parsed = parse_meme_ideation_output(raw_text, debug=request.debug)
    survivors, scorecards, judge_warnings = _judge_candidates(
        parsed.candidates,
        mutation_plan=mutation_plan,
        requested_count=request.requested_count,
    )
    warnings = list(knowledge_pack.warnings) + parsed.warnings
    if parsed.candidates and not survivors:
        warnings.append("generation succeeded but every candidate was rejected as too mid")
    if request.debug and scorecards:
        judge_warnings.extend(
            f"candidate {scorecard.candidate_index}: total={scorecard.total_score:.2f}, normieRisk={scorecard.normie_contamination_risk:.2f}, accepted={scorecard.accepted}"
            for scorecard in scorecards[: request.requested_count]
        )
    return MemeIdeationResponse(
        candidates=survivors,
        provider=provider_name,
        model=resolved_model,
        preset=request.preset,
        schema_version=MEME_IDEATION_SCHEMA_VERSION,
        prompt_version=MEME_IDEATION_PROMPT_VERSION,
        warnings=warnings,
        raw_text=parsed.raw_text,
        knowledge_pack_version=knowledge_pack.version,
        judge_warnings=judge_warnings,
        artifact_shell=mutation_plan.artifact_shell_candidates[0] if mutation_plan.artifact_shell_candidates else None,
        mutation_notes=list(mutation_plan.mutation_notes),
    )


async def refine_memes(
    *,
    provider_name: str,
    provider: Provider,
    request: MemeRefinementRequest,
) -> MemeRefinementResponse:
    if provider_name not in _LOCAL_PROVIDER_IDS:
        raise ValueError(f"provider {provider_name} is not a supported local meme ideation provider")

    ideation_request = request.ideation_request
    knowledge_context = build_meme_knowledge_index()
    knowledge_pack = build_meme_knowledge_pack(
        knowledge_context,
        topic=ideation_request.topic,
        trend_summary=ideation_request.trend_summary,
        image_springboard=ideation_request.image_springboard,
        tone_hints=ideation_request.tone_hints,
    )
    mutation_plan = build_mutation_plan(ideation_request, knowledge_pack)
    system_prompt = build_meme_refinement_system_prompt(request, knowledge_pack=knowledge_pack, mutation_plan=mutation_plan)
    user_prompt = build_meme_refinement_user_prompt(request, knowledge_pack=knowledge_pack, mutation_plan=mutation_plan)
    resolved_model = await _resolve_model(provider, ideation_request.model)

    raw_text = await _run_provider_text(provider=provider, prompt=user_prompt, model=resolved_model, system_prompt=system_prompt)
    parsed = parse_meme_refinement_output(raw_text, debug=request.debug)
    survivors, scorecards, judge_warnings = _judge_candidates(
        parsed.suggested_candidates,
        mutation_plan=mutation_plan,
        requested_count=min(max(1, len(request.current_candidates) or 1), _MAX_REQUESTED_COUNT),
    )
    warnings = list(knowledge_pack.warnings) + parsed.warnings
    if parsed.suggested_candidates and not survivors:
        warnings.append("refinement produced candidates, but every rewrite was rejected as too mid")
    if request.debug and scorecards:
        judge_warnings.extend(
            f"candidate {scorecard.candidate_index}: total={scorecard.total_score:.2f}, normieRisk={scorecard.normie_contamination_risk:.2f}, accepted={scorecard.accepted}"
            for scorecard in scorecards[: max(1, len(request.current_candidates))]
        )
    return MemeRefinementResponse(
        assistant_reply=parsed.assistant_reply,
        suggested_candidates=survivors,
        provider=provider_name,
        model=resolved_model,
        preset=ideation_request.preset,
        schema_version=MEME_IDEATION_SCHEMA_VERSION,
        prompt_version=MEME_IDEATION_PROMPT_VERSION,
        warnings=warnings,
        raw_text=parsed.raw_text,
        knowledge_pack_version=knowledge_pack.version,
        judge_warnings=judge_warnings,
        artifact_shell=mutation_plan.artifact_shell_candidates[0] if mutation_plan.artifact_shell_candidates else None,
        mutation_notes=list(mutation_plan.mutation_notes),
    )
