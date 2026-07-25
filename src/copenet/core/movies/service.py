"""Application service for importing, enriching, analyzing, and recommending movies."""

from __future__ import annotations

from collections import defaultdict
import math
from pathlib import Path
import statistics
from typing import Any

from copenet.core.movies.matching import match_decision, normalize_title, rank_candidates, search_query
from copenet.core.movies.store import MovieLabStore, catalog_key
from copenet.core.movies.tmdb import TmdbClient
from copenet.core.movies.xlsx_import import import_watched_workbook


class MovieLabService:
    def __init__(self, store: MovieLabStore, tmdb: TmdbClient | None = None) -> None:
        self.store = store
        self.tmdb = tmdb or TmdbClient()

    def import_workbook(self, source: Path) -> dict[str, Any]:
        watched = import_watched_workbook(source)
        state = self.store.replace_watched(watched, source=source)
        return {
            "source": state["source"],
            "imported": len(watched),
            "fullyRated": sum(bool(item["ratingComplete"]) for item in watched),
            "unrated": sum(not bool(item["ratingComplete"]) for item in watched),
        }

    def sync_tmdb(self, *, limit: int | None = None, refresh: bool = False) -> dict[str, Any]:
        if not self.tmdb.configured:
            raise ValueError("TMDB is not configured; set TMDB_ACCESS_TOKEN or TMDB_API_KEY in .env")
        state = self.store.state()
        watched = list(state["watched"])
        if not watched:
            raise ValueError("no watched movies imported; run `copenet movies import` first")
        selected_rows = watched[:limit] if limit is not None and limit >= 0 else watched
        summary = {"processed": 0, "matched": 0, "review": 0, "enriched": 0, "preservedManual": 0}
        for item in selected_rows:
            row = int(item["sourceRow"])
            existing = state["matches"].get(str(row))
            if existing and existing.get("method") == "manual" and not refresh:
                decision = existing
                summary["preservedManual"] += 1
            elif existing and existing.get("status") == "matched" and not refresh:
                decision = existing
            else:
                query, _ = search_query(str(item["originalTitle"]))
                ranked = rank_candidates(str(item["originalTitle"]), self.tmdb.search_multi(query))
                decision = match_decision(str(item["originalTitle"]), ranked)
                self.store.save_match(row, decision)
            summary["processed"] += 1
            if decision.get("status") != "matched" or not isinstance(decision.get("selected"), dict):
                summary["review"] += 1
                continue
            summary["matched"] += 1
            selected = decision["selected"]
            key = catalog_key(str(selected["mediaType"]), int(selected["tmdbId"]))
            if key in state["catalog"] and not refresh:
                continue
            raw_details = self.tmdb.details(str(selected["mediaType"]), int(selected["tmdbId"]))
            self.store.save_catalog_item(_normalize_details(str(selected["mediaType"]), raw_details))
            state["catalog"][key] = True
            summary["enriched"] += 1
        self.store.prune_catalog_to_matches()
        return summary

    def resolve_match(self, *, source_row: int, media_type: str, tmdb_id: int) -> dict[str, Any]:
        state = self.store.state()
        watched = next((item for item in state["watched"] if int(item["sourceRow"]) == source_row), None)
        if watched is None:
            raise ValueError(f"no watched entry at source row {source_row}")
        details = _normalize_details(media_type, self.tmdb.details(media_type, tmdb_id))
        selected = {
            "tmdbId": tmdb_id,
            "mediaType": media_type,
            "title": details["title"],
            "originalTitle": details["originalTitle"],
            "releaseDate": details["releaseDate"],
            "posterPath": details["posterPath"],
            "titleSimilarity": None,
        }
        match = {
            "status": "matched",
            "method": "manual",
            "reason": "operator-selected TMDB identity",
            "selected": selected,
            "candidates": [],
        }
        self.store.save_match(source_row, match)
        self.store.save_catalog_item(details)
        return {"sourceRow": source_row, "originalTitle": watched["originalTitle"], "selected": selected}

    def status(self) -> dict[str, Any]:
        state = self.store.state()
        matches = list(state["matches"].values())
        return {
            "store": str(self.store.path),
            "source": state.get("source"),
            "watched": len(state["watched"]),
            "fullyRated": sum(bool(item.get("ratingComplete")) for item in state["watched"]),
            "matched": sum(item.get("status") == "matched" for item in matches),
            "needsReview": sum(item.get("status") == "review" for item in matches),
            "notProcessed": max(len(state["watched"]) - len(matches), 0),
            "catalogItems": len(state["catalog"]),
            "recommendations": len(state["recommendations"]),
            "tmdbConfigured": self.tmdb.configured,
        }

    def review_queue(self) -> list[dict[str, Any]]:
        state = self.store.state()
        by_row = {int(item["sourceRow"]): item for item in state["watched"]}
        queue: list[dict[str, Any]] = []
        for row_text, match in state["matches"].items():
            if match.get("status") != "review":
                continue
            row = int(row_text)
            watched = by_row.get(row, {})
            queue.append(
                {
                    "sourceRow": row,
                    "originalTitle": watched.get("originalTitle"),
                    "reason": match.get("reason"),
                    "candidates": match.get("candidates", []),
                }
            )
        queue.sort(key=lambda item: item["sourceRow"])
        return queue

    def report(self) -> dict[str, Any]:
        state = self.store.state()
        rated = [item for item in state["watched"] if item.get("ratingComplete") and item.get("finalScore") is not None]
        component_means = {}
        for key in ("plot", "acting", "pacing", "cinematography", "score", "impact"):
            values = [float(item["components"][key]) for item in rated if item["components"].get(key) is not None]
            component_means[key] = round(statistics.mean(values), 2) if values else None
        paired = [
            (float(item["initialRating"]), float(item["finalScore"]))
            for item in rated
            if item.get("initialRating") is not None
        ]
        genre_scores: dict[str, list[float]] = defaultdict(list)
        for item in rated:
            match = state["matches"].get(str(item["sourceRow"]), {})
            selected = match.get("selected") if isinstance(match, dict) else None
            if not isinstance(selected, dict):
                continue
            catalog = state["catalog"].get(catalog_key(selected["mediaType"], int(selected["tmdbId"])), {})
            for genre in catalog.get("genres", []):
                if isinstance(genre, dict) and genre.get("name"):
                    genre_scores[str(genre["name"])].append(float(item["finalScore"]))
        genre_summary = [
            {"genre": genre, "watched": len(scores), "averageFinalScore": round(statistics.mean(scores), 2)}
            for genre, scores in genre_scores.items()
        ]
        genre_summary.sort(key=lambda item: (item["averageFinalScore"], item["watched"]), reverse=True)
        top = sorted(rated, key=lambda item: float(item["finalScore"]), reverse=True)[:10]
        return {
            "watched": len(state["watched"]),
            "fullyRated": len(rated),
            "averageFinalScore": round(statistics.mean(float(item["finalScore"]) for item in rated), 2) if rated else None,
            "componentMeans": component_means,
            "initialToFinalCorrelation": _pearson(paired),
            "topRated": [
                {"title": item["originalTitle"], "finalScore": item["finalScore"]}
                for item in top
            ],
            "genrePerformance": genre_summary,
        }

    def recommend(self, *, limit: int = 20, exploration_share: float = 0.25) -> list[dict[str, Any]]:
        if limit <= 0:
            return []
        exploration_share = min(max(exploration_share, 0.0), 1.0)
        state = self.store.state()
        seeds = _recommendation_seeds(state)[:10]
        if not seeds:
            raise ValueError("no rated TMDB matches are available; run `copenet movies sync` first")
        watched_keys = {
            catalog_key(selected["mediaType"], int(selected["tmdbId"]))
            for match in state["matches"].values()
            if isinstance(match, dict) and isinstance((selected := match.get("selected")), dict)
        }
        favorite_genres = _favorite_genre_ids(seeds, state["catalog"])
        genre_counts = _watched_genre_counts(state)
        candidates: dict[str, dict[str, Any]] = {}
        for seed in seeds:
            selected = seed["selected"]
            seed_weight = float(seed["finalScore"]) / 10.0
            for rank, raw in enumerate(
                self.tmdb.recommendations(selected["mediaType"], int(selected["tmdbId"])),
                start=1,
            ):
                media_type = str(raw.get("media_type") or selected["mediaType"])
                if media_type not in {"movie", "tv"} or raw.get("id") is None:
                    continue
                if int(raw.get("vote_count") or 0) < 250 or float(raw.get("vote_average") or 0.0) < 6.5:
                    continue
                key = catalog_key(media_type, int(raw["id"]))
                if key in watched_keys:
                    continue
                candidate = candidates.setdefault(key, _recommendation_candidate(media_type, raw))
                candidate["seedSignal"] += seed_weight / math.sqrt(rank)
                candidate["becauseOf"].append(seed["title"])
        for candidate in candidates.values():
            overlap = sorted(set(candidate["genreIds"]) & favorite_genres)
            candidate["bridgeGenreIds"] = overlap
            novel_genres = sorted(
                genre
                for genre in candidate["genreIds"]
                if genre != 10770 and genre_counts.get(genre, 0) <= 5
            )
            candidate["novelGenreIds"] = novel_genres
            candidate["exploration"] = bool(novel_genres)
            quality = min(float(candidate["voteAverage"]) / 10.0, 1.0)
            confidence = min(math.log10(max(float(candidate["voteCount"]), 1.0)) / 4.0, 1.0)
            family_penalty = 0.25 if _looks_like_same_franchise(candidate["title"], candidate["becauseOf"]) else 0.0
            candidate["recommendationScore"] = round(
                candidate["seedSignal"] * 0.55 + quality * 0.3 + confidence * 0.15 - family_penalty,
                4,
            )
            candidate["becauseOf"] = list(dict.fromkeys(candidate["becauseOf"]))[:3]
            lane = "step outside your box" if candidate["exploration"] else "inside your lane"
            candidate["reason"] = f"{lane}; connected through {', '.join(candidate['becauseOf'])}"
        ranked = sorted(candidates.values(), key=lambda item: item["recommendationScore"], reverse=True)
        exploration_target = round(limit * exploration_share)
        exploration = _select_diverse(
            [item for item in ranked if item["exploration"]],
            exploration_target,
            max_per_primary_seed=2,
        )
        selected_keys = {catalog_key(item["mediaType"], item["tmdbId"]) for item in exploration}
        familiar = _select_diverse(
            [
                item for item in ranked
                if catalog_key(item["mediaType"], item["tmdbId"]) not in selected_keys
            ],
            max(limit - len(exploration), 0),
            max_per_primary_seed=3,
        )
        recommendations = sorted(exploration + familiar, key=lambda item: item["recommendationScore"], reverse=True)[:limit]
        self.store.save_recommendations(recommendations)
        return recommendations


def _normalize_details(media_type: str, raw: dict[str, Any]) -> dict[str, Any]:
    credits = raw.get("credits") if isinstance(raw.get("credits"), dict) else {}
    crew = credits.get("crew") if isinstance(credits.get("crew"), list) else []
    cast = credits.get("cast") if isinstance(credits.get("cast"), list) else []
    keywords_payload = raw.get("keywords") if isinstance(raw.get("keywords"), dict) else {}
    keywords = keywords_payload.get("keywords") or keywords_payload.get("results") or []
    countries = raw.get("production_countries") or raw.get("origin_country") or []
    return {
        "tmdbId": int(raw["id"]),
        "mediaType": media_type,
        "title": str(raw.get("title") or raw.get("name") or "").strip(),
        "originalTitle": str(raw.get("original_title") or raw.get("original_name") or "").strip(),
        "releaseDate": str(raw.get("release_date") or raw.get("first_air_date") or "").strip(),
        "overview": str(raw.get("overview") or "").strip(),
        "tagline": str(raw.get("tagline") or "").strip(),
        "posterPath": raw.get("poster_path"),
        "backdropPath": raw.get("backdrop_path"),
        "genres": [
            {"id": int(item["id"]), "name": str(item["name"])}
            for item in raw.get("genres", [])
            if isinstance(item, dict) and item.get("id") is not None and item.get("name")
        ],
        "keywords": [
            {"id": int(item["id"]), "name": str(item["name"])}
            for item in keywords
            if isinstance(item, dict) and item.get("id") is not None and item.get("name")
        ],
        "directors": [
            {"id": int(item["id"]), "name": str(item["name"])}
            for item in crew
            if isinstance(item, dict) and item.get("job") == "Director" and item.get("id") is not None
        ],
        "cast": [
            {"id": int(item["id"]), "name": str(item["name"]), "character": str(item.get("character") or "")}
            for item in cast[:12]
            if isinstance(item, dict) and item.get("id") is not None and item.get("name")
        ],
        "runtimeMinutes": raw.get("runtime") or next(iter(raw.get("episode_run_time") or []), None),
        "originalLanguage": str(raw.get("original_language") or "").strip(),
        "countries": [str(item.get("iso_3166_1") or "") if isinstance(item, dict) else str(item) for item in countries],
        "voteAverage": float(raw.get("vote_average") or 0.0),
        "voteCount": int(raw.get("vote_count") or 0),
        "popularity": float(raw.get("popularity") or 0.0),
    }


def _pearson(pairs: list[tuple[float, float]]) -> float | None:
    if len(pairs) < 2:
        return None
    xs, ys = zip(*pairs, strict=True)
    x_mean, y_mean = statistics.mean(xs), statistics.mean(ys)
    numerator = sum((x - x_mean) * (y - y_mean) for x, y in pairs)
    denominator = math.sqrt(sum((x - x_mean) ** 2 for x in xs) * sum((y - y_mean) ** 2 for y in ys))
    return round(numerator / denominator, 3) if denominator else None


def _recommendation_seeds(state: dict[str, Any]) -> list[dict[str, Any]]:
    seeds = []
    for item in state["watched"]:
        if not item.get("ratingComplete") or item.get("finalScore") is None:
            continue
        match = state["matches"].get(str(item["sourceRow"]), {})
        selected = match.get("selected") if isinstance(match, dict) else None
        if isinstance(selected, dict):
            seeds.append({"title": item["originalTitle"], "finalScore": item["finalScore"], "selected": selected})
    return sorted(seeds, key=lambda item: float(item["finalScore"]), reverse=True)


def _favorite_genre_ids(seeds: list[dict[str, Any]], catalog: dict[str, Any]) -> set[int]:
    weighted: dict[int, float] = defaultdict(float)
    for seed in seeds:
        selected = seed["selected"]
        details = catalog.get(catalog_key(selected["mediaType"], int(selected["tmdbId"])), {})
        for genre in details.get("genres", []):
            if isinstance(genre, dict) and genre.get("id") is not None:
                weighted[int(genre["id"])] += float(seed["finalScore"])
    return {genre for genre, _ in sorted(weighted.items(), key=lambda item: item[1], reverse=True)[:6]}


def _watched_genre_counts(state: dict[str, Any]) -> dict[int, int]:
    counts: dict[int, int] = defaultdict(int)
    for item in state["watched"]:
        match = state["matches"].get(str(item["sourceRow"]), {})
        selected = match.get("selected") if isinstance(match, dict) else None
        if not isinstance(selected, dict):
            continue
        details = state["catalog"].get(catalog_key(selected["mediaType"], int(selected["tmdbId"])), {})
        for genre in details.get("genres", []):
            if isinstance(genre, dict) and genre.get("id") is not None:
                counts[int(genre["id"])] += 1
    return counts


def _looks_like_same_franchise(title: str, seed_titles: list[str]) -> bool:
    candidate_words = {word for word in normalize_title(title).split() if len(word) >= 4}
    for seed_title in seed_titles:
        seed_words = {word for word in normalize_title(seed_title).split() if len(word) >= 4}
        if len(candidate_words & seed_words) >= 2:
            return True
    return False


def _recommendation_candidate(media_type: str, raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "tmdbId": int(raw["id"]),
        "mediaType": media_type,
        "title": str(raw.get("title") or raw.get("name") or "").strip(),
        "releaseDate": str(raw.get("release_date") or raw.get("first_air_date") or "").strip(),
        "overview": str(raw.get("overview") or "").strip(),
        "posterPath": raw.get("poster_path"),
        "genreIds": [int(value) for value in raw.get("genre_ids", []) if isinstance(value, int)],
        "voteAverage": float(raw.get("vote_average") or 0.0),
        "voteCount": int(raw.get("vote_count") or 0),
        "popularity": float(raw.get("popularity") or 0.0),
        "seedSignal": 0.0,
        "becauseOf": [],
    }


def _select_diverse(
    ranked: list[dict[str, Any]],
    limit: int,
    *,
    max_per_primary_seed: int,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    seed_counts: dict[str, int] = defaultdict(int)
    deferred: list[dict[str, Any]] = []
    for item in ranked:
        primary_seed = str(next(iter(item.get("becauseOf") or []), "unknown"))
        if seed_counts[primary_seed] >= max_per_primary_seed:
            deferred.append(item)
            continue
        selected.append(item)
        seed_counts[primary_seed] += 1
        if len(selected) >= limit:
            return selected
    for item in deferred:
        selected.append(item)
        if len(selected) >= limit:
            break
    return selected
