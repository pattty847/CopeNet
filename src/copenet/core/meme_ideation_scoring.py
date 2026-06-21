"""Local scoring and anti-mid filtering for meme candidates."""

from __future__ import annotations

from dataclasses import replace

from .meme_ideation_constants import (
    _ARTIFACT_FORMATS,
    _DOMAIN_KEYWORDS,
    _FAKE_AUTHORITY_WORDS,
    _NORMIE_RISK_PHRASES,
    _REWRITE_DETAILS,
)
from .meme_ideation_models import JudgeScorecard, MemeIdeationCandidate, MutationPlan


def _score_artifact_shell(candidate: MemeIdeationCandidate, mutation_plan: MutationPlan) -> float:
    haystack = f"{candidate.format} {candidate.direction} {candidate.text} {candidate.notes or ''}".lower()
    score = 0.0
    if candidate.format.lower() in _ARTIFACT_FORMATS:
        score += 1.6
    if candidate.needs_visual_context:
        score += 0.6
    for shell in mutation_plan.artifact_shell_candidates:
        if shell.lower() in haystack:
            score += 0.5
    return min(score, 3.0)


def _score_lexical_novelty(candidate: MemeIdeationCandidate) -> float:
    text = candidate.text
    words = [word.strip(".,:;!?()[]{}\"'").lower() for word in text.split()]
    long_words = sum(1 for word in words if len(word) >= 9)
    weird_words = sum(1 for word in words if "-" in word or any(char.isdigit() for char in word))
    return min(0.4 * long_words + 0.6 * weird_words, 3.0)


def _score_domain_collision(candidate: MemeIdeationCandidate, mutation_plan: MutationPlan) -> float:
    haystack = f"{candidate.direction} {candidate.text} {candidate.notes or ''}".lower()
    score = 0.0
    for domain in mutation_plan.domain_collision_candidates:
        keywords = _DOMAIN_KEYWORDS.get(domain, set())
        if any(keyword in haystack for keyword in keywords):
            score += 1.0
    return min(score, 3.0)


def _score_delayed_recognition(candidate: MemeIdeationCandidate) -> float:
    text = candidate.text
    score = 0.0
    if len(text.split()) >= 8:
        score += 0.8
    if any(char.isdigit() for char in text):
        score += 0.8
    if "/" in text or "before" in text.lower() or "pending" in text.lower():
        score += 0.8
    return min(score, 3.0)


def _score_fake_authority(candidate: MemeIdeationCandidate) -> float:
    haystack = f"{candidate.direction} {candidate.text} {candidate.notes or ''}".lower()
    return min(sum(0.5 for word in _FAKE_AUTHORITY_WORDS if word in haystack), 3.0)


def _score_implied_lore(candidate: MemeIdeationCandidate) -> float:
    haystack = f"{candidate.direction} {candidate.text} {candidate.notes or ''}".lower()
    score = 0.0
    if candidate.notes:
        score += 0.8
    if any(term in haystack for term in ("again", "still", "flagged", "review", "bloodline", "noticed", "committee")):
        score += 1.0
    if candidate.optional_caption:
        score += 0.4
    return min(score, 3.0)


def _score_normie_risk(candidate: MemeIdeationCandidate) -> float:
    haystack = f"{candidate.direction} {candidate.text} {candidate.notes or ''} {candidate.optional_caption or ''}".lower()
    risk = 0.0
    for phrase in _NORMIE_RISK_PHRASES:
        if phrase in haystack:
            risk += 1.1
    if "#" in haystack:
        risk += 2.2
    if len(candidate.text.split()) < 5:
        risk += 0.5
    if candidate.optional_caption and len(candidate.optional_caption.split()) > 8:
        risk += 0.9
    if candidate.optional_caption and any(term in candidate.optional_caption.lower() for term in ("don't forget", "the data doesn't lie", "it's not just", "if you aren't")):
        risk += 0.9
    if candidate.notes and any(term in candidate.notes.lower() for term in ("the core hit", "should look", "the jump from", "the escalation from", "the visual should", "place this text over")):
        risk += 0.9
    if candidate.format.lower().startswith("internal memo"):
        risk += 0.4
    return min(risk, 4.0)


def judge_candidate(candidate: MemeIdeationCandidate, *, candidate_index: int, mutation_plan: MutationPlan) -> JudgeScorecard:
    artifact_shell_strength = _score_artifact_shell(candidate, mutation_plan)
    lexical_novelty = _score_lexical_novelty(candidate)
    domain_collision_strength = _score_domain_collision(candidate, mutation_plan)
    delayed_recognition = _score_delayed_recognition(candidate)
    fake_authority_energy = _score_fake_authority(candidate)
    implied_lore_density = _score_implied_lore(candidate)
    normie_contamination_risk = _score_normie_risk(candidate)
    total_score = (
        artifact_shell_strength
        + lexical_novelty
        + domain_collision_strength
        + delayed_recognition
        + fake_authority_energy
        + implied_lore_density
        - normie_contamination_risk
    )
    warnings: list[str] = []
    if normie_contamination_risk >= 1.4:
        warnings.append("candidate reads too smooth or normie-safe")
    if artifact_shell_strength < 0.8:
        warnings.append("candidate lacks a strong artifact shell")
    accepted = total_score >= 5.6 and normie_contamination_risk < 1.5
    return JudgeScorecard(
        candidate_index=candidate_index,
        artifact_shell_strength=artifact_shell_strength,
        lexical_novelty=lexical_novelty,
        domain_collision_strength=domain_collision_strength,
        delayed_recognition=delayed_recognition,
        fake_authority_energy=fake_authority_energy,
        implied_lore_density=implied_lore_density,
        normie_contamination_risk=normie_contamination_risk,
        total_score=total_score,
        accepted=accepted,
        warnings=tuple(warnings),
    )


def rewrite_candidate_once(candidate: MemeIdeationCandidate, mutation_plan: MutationPlan) -> MemeIdeationCandidate:
    if any(char.isdigit() for char in candidate.text) and any(domain.lower() in candidate.text.lower() for domain in mutation_plan.domain_collision_candidates):
        return candidate
    chosen_domain = mutation_plan.domain_collision_candidates[0] if mutation_plan.domain_collision_candidates else "compliance"
    detail = _REWRITE_DETAILS.get(chosen_domain, f"under {chosen_domain} review")
    if detail.lower() in candidate.text.lower():
        return candidate
    new_text = candidate.text.rstrip(" .")
    separator = " / " if "/" not in new_text else " // "
    new_text = f"{new_text}{separator}{detail}"
    notes = candidate.notes or ""
    extra_note = f"rewritten once to increase domain collision via {chosen_domain}"
    merged_notes = f"{notes}; {extra_note}".strip("; ")
    return replace(candidate, text=new_text, notes=merged_notes)


def _judge_candidates(
    candidates: list[MemeIdeationCandidate],
    *,
    mutation_plan: MutationPlan,
    requested_count: int,
) -> tuple[list[MemeIdeationCandidate], list[JudgeScorecard], list[str]]:
    scorecards: list[JudgeScorecard] = []
    accepted: list[tuple[JudgeScorecard, MemeIdeationCandidate]] = []
    borderline: list[tuple[JudgeScorecard, MemeIdeationCandidate]] = []
    warnings: list[str] = []
    for index, candidate in enumerate(candidates):
        scorecard = judge_candidate(candidate, candidate_index=index, mutation_plan=mutation_plan)
        scorecards.append(scorecard)
        if scorecard.accepted:
            accepted.append((scorecard, candidate))
            continue
        if scorecard.total_score >= 4.6 and scorecard.normie_contamination_risk < 2.0:
            rewritten = rewrite_candidate_once(candidate, mutation_plan)
            rewritten_scorecard = judge_candidate(rewritten, candidate_index=index, mutation_plan=mutation_plan)
            scorecards.append(rewritten_scorecard)
            if rewritten_scorecard.accepted:
                accepted.append((rewritten_scorecard, rewritten))
            else:
                borderline.append((rewritten_scorecard, rewritten))
        else:
            borderline.append((scorecard, candidate))

    accepted.sort(key=lambda item: item[0].total_score, reverse=True)
    survivors = [candidate for _, candidate in accepted[:requested_count]]
    if not survivors and borderline:
        borderline.sort(key=lambda item: item[0].total_score, reverse=True)
        top_scorecard, top_candidate = borderline[0]
        if top_scorecard.total_score >= 6.8 and top_scorecard.normie_contamination_risk <= 1.9:
            survivors = [top_candidate]
            warnings.append("judge escalated one borderline candidate to avoid an empty result set")
    if len(survivors) < requested_count:
        warnings.append(f"judge only found {len(survivors)} candidates above the anti-mid threshold")
    return survivors, scorecards, warnings
