"""Model-output parsers for meme ideation."""

from __future__ import annotations

import json

from .meme_ideation_models import (
    MemeIdeationCandidate,
    MemeIdeationParseResult,
    MemeRefinementParseResult,
    _clean_optional_text,
)


def _candidate_from_obj(item: object) -> MemeIdeationCandidate | None:
    if not isinstance(item, dict):
        return None
    direction = _clean_optional_text(item.get("direction"))
    format_name = _clean_optional_text(item.get("format"))
    text = _clean_optional_text(item.get("text"))
    if not direction or not format_name or not text:
        return None
    optional_caption = _clean_optional_text(item.get("optional_caption"))
    notes = _clean_optional_text(item.get("notes"))
    needs_visual_context = bool(item.get("needs_visual_context"))
    return MemeIdeationCandidate(
        direction=direction,
        format=format_name,
        text=text,
        optional_caption=optional_caption,
        needs_visual_context=needs_visual_context,
        notes=notes,
    )


def _extract_json_candidate(raw_text: str) -> str:
    text = raw_text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    start_object = text.find("{")
    end_object = text.rfind("}")
    start_array = text.find("[")
    end_array = text.rfind("]")
    object_candidate = text[start_object : end_object + 1] if start_object != -1 and end_object > start_object else ""
    array_candidate = text[start_array : end_array + 1] if start_array != -1 and end_array > start_array else ""
    if object_candidate and array_candidate:
        return object_candidate if len(object_candidate) >= len(array_candidate) else array_candidate
    return object_candidate or array_candidate or text


def _strip_markdown_fences(raw_text: str) -> str:
    text = raw_text.strip()
    if not text.startswith("```"):
        return text
    lines = text.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def parse_meme_ideation_output(raw_text: str, *, debug: bool) -> MemeIdeationParseResult:
    warnings: list[str] = []
    payload = None
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError:
        try:
            payload = json.loads(_strip_markdown_fences(raw_text))
        except json.JSONDecodeError:
            try:
                payload = json.loads(_extract_json_candidate(raw_text))
                warnings.append("model output required light JSON cleanup before parsing")
            except json.JSONDecodeError:
                raw = raw_text if debug else None
                return MemeIdeationParseResult(
                    candidates=[],
                    warnings=["model output was not valid JSON"],
                    raw_text=raw,
                )

    candidate_rows: object
    if isinstance(payload, dict):
        candidate_rows = payload.get("candidates", [])
    else:
        candidate_rows = payload

    if not isinstance(candidate_rows, list):
        raw = raw_text if debug else None
        return MemeIdeationParseResult(
            candidates=[],
            warnings=["parsed JSON did not contain a candidates array"],
            raw_text=raw,
        )

    candidates: list[MemeIdeationCandidate] = []
    invalid_count = 0
    for item in candidate_rows:
        candidate = _candidate_from_obj(item)
        if candidate is None:
            invalid_count += 1
            continue
        candidates.append(candidate)

    if invalid_count:
        warnings.append(f"ignored {invalid_count} malformed candidate entries")
    if not candidates:
        warnings.append("no valid meme candidates were recovered from model output")

    return MemeIdeationParseResult(
        candidates=candidates,
        warnings=warnings,
        raw_text=raw_text if debug else None,
    )


def parse_meme_refinement_output(raw_text: str, *, debug: bool) -> MemeRefinementParseResult:
    warnings: list[str] = []
    payload = None
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError:
        try:
            payload = json.loads(_strip_markdown_fences(raw_text))
        except json.JSONDecodeError:
            try:
                payload = json.loads(_extract_json_candidate(raw_text))
                warnings.append("model output required light JSON cleanup before parsing")
            except json.JSONDecodeError:
                return MemeRefinementParseResult(
                    assistant_reply="I couldn't turn that refinement pass into structured output, but the model did respond.",
                    suggested_candidates=[],
                    warnings=["model output was not valid JSON"],
                    raw_text=raw_text if debug else None,
                )
    if not isinstance(payload, dict):
        return MemeRefinementParseResult(
            assistant_reply="I couldn't recover a structured refinement response.",
            suggested_candidates=[],
            warnings=["parsed JSON did not contain an object response"],
            raw_text=raw_text if debug else None,
        )
    assistant_reply = _clean_optional_text(payload.get("assistantReply") or payload.get("assistant_reply")) or "Refinement suggestions ready."
    candidate_rows = payload.get("suggestedCandidates") or payload.get("suggested_candidates") or []
    suggested_candidates: list[MemeIdeationCandidate] = []
    invalid_count = 0
    if isinstance(candidate_rows, list):
        for item in candidate_rows:
            candidate = _candidate_from_obj(item)
            if candidate is None:
                invalid_count += 1
                continue
            suggested_candidates.append(candidate)
    elif candidate_rows:
        warnings.append("suggestedCandidates was not a list")
    if invalid_count:
        warnings.append(f"ignored {invalid_count} malformed suggested candidate entries")
    return MemeRefinementParseResult(
        assistant_reply=assistant_reply,
        suggested_candidates=suggested_candidates,
        warnings=warnings,
        raw_text=raw_text if debug else None,
    )
