"""Conservative watched-title matching against TMDB multi-search results."""

from __future__ import annotations

from difflib import SequenceMatcher
import re
import unicodedata
from typing import Any


_TITLE_ALIASES = {
    "blacklist": "The Blacklist",
    "harry potter chamber of secrets": "Harry Potter and the Chamber of Secrets",
    "harry potter deathly hallows part 1": "Harry Potter and the Deathly Hallows: Part 1",
    "harry potter half blood prince": "Harry Potter and the Half-Blood Prince",
    "harry potter prisoner of azkaban": "Harry Potter and the Prisoner of Azkaban",
    "harry potter sorcerer s stone": "Harry Potter and the Philosopher's Stone",
    "house m d": "House",
    "old boy": "Oldboy",
    "tenent": "Tenet",
    "water world": "Waterworld",
    "wolf of wall street": "The Wolf of Wall Street",
}


def rank_candidates(original_title: str, results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    query, media_hint = search_query(original_title)
    normalized_query = normalize_title(query)
    ranked: list[dict[str, Any]] = []
    for raw in results:
        media_type = str(raw.get("media_type") or "")
        if media_type not in {"movie", "tv"} or raw.get("id") is None:
            continue
        titles = [raw.get("title"), raw.get("name"), raw.get("original_title"), raw.get("original_name")]
        similarities = [
            SequenceMatcher(None, normalized_query, normalize_title(str(title))).ratio()
            for title in titles
            if title
        ]
        if not similarities:
            continue
        title_similarity = max(similarities)
        media_bonus = 0.04 if media_hint == media_type else 0.0
        popularity = max(float(raw.get("popularity") or 0.0), 0.0)
        rank_score = min(title_similarity + media_bonus, 1.0) + min(popularity, 100.0) / 10000.0
        ranked.append(
            {
                "tmdbId": int(raw["id"]),
                "mediaType": media_type,
                "title": str(raw.get("title") or raw.get("name") or "").strip(),
                "originalTitle": str(raw.get("original_title") or raw.get("original_name") or "").strip(),
                "releaseDate": str(raw.get("release_date") or raw.get("first_air_date") or "").strip(),
                "overview": str(raw.get("overview") or "").strip(),
                "posterPath": raw.get("poster_path"),
                "popularity": popularity,
                "voteAverage": float(raw.get("vote_average") or 0.0),
                "voteCount": int(raw.get("vote_count") or 0),
                "titleSimilarity": round(title_similarity, 4),
                "rankScore": round(rank_score, 4),
            }
        )
    ranked.sort(key=lambda item: (item["rankScore"], item["popularity"]), reverse=True)
    return ranked


def match_decision(original_title: str, ranked: list[dict[str, Any]]) -> dict[str, Any]:
    query, media_hint = search_query(original_title)
    normalized_query = normalize_title(query)
    candidates = ranked[:5]
    exact = [item for item in candidates if normalize_title(item["title"]) == normalized_query]
    hinted_exact = [item for item in exact if item["mediaType"] == media_hint]
    exact_pool = hinted_exact or exact
    selected: dict[str, Any] | None = None
    reason = "no plausible TMDB result"
    if len(exact_pool) == 1:
        selected = exact_pool[0]
        reason = "unique exact title match"
    elif len(exact_pool) > 1:
        by_votes = sorted(exact_pool, key=lambda item: int(item["voteCount"]), reverse=True)
        dominant, runner = by_votes[:2]
        vote_dominance = int(dominant["voteCount"]) >= 500 and int(dominant["voteCount"]) >= max(int(runner["voteCount"]), 1) * 8
        popularity_dominance = float(dominant["popularity"]) >= 5.0 and float(dominant["popularity"]) >= max(float(runner["popularity"]), 0.1) * 25.0
        if vote_dominance or popularity_dominance:
            selected = dominant
            reason = "exact title match with a dominant canonical result"
        else:
            reason = "multiple TMDB titles match exactly; a release year is needed"
    elif candidates:
        top = candidates[0]
        runner_score = float(candidates[1]["titleSimilarity"]) if len(candidates) > 1 else 0.0
        gap = float(top["titleSimilarity"]) - runner_score
        if float(top["titleSimilarity"]) >= 0.92 and gap >= 0.08:
            selected = top
            reason = "high-confidence fuzzy title match"
        else:
            reason = "top TMDB result is not confident enough for automatic matching"
    return {
        "status": "matched" if selected else "review",
        "method": "automatic" if selected else None,
        "reason": reason,
        "selected": selected,
        "candidates": candidates,
    }


def search_query(original_title: str) -> tuple[str, str | None]:
    title = original_title.strip()
    lowered = title.lower()
    media_hint = "tv" if any(marker in lowered for marker in ("tv show", "(show)", "| free bert")) else None
    title = re.sub(r"\btv\s+show\b", "", title, flags=re.IGNORECASE)
    title = re.sub(r"\(show\)", "", title, flags=re.IGNORECASE)
    title = title.replace("|", " ")
    title = re.sub(r"\s+", " ", title).strip(" -")
    if "free bert" in lowered:
        title = "Free Bert"
    title = _TITLE_ALIASES.get(normalize_title(title), title)
    return title, media_hint


def normalize_title(title: str) -> str:
    ascii_title = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", " ", ascii_title.lower()).strip()
