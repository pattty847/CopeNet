"""CLI surface for the personal Movie Lab."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from copenet._paths import default_movies_dir
from copenet.core.movies import MovieLabService, MovieLabStore


def configure_movies_parser(subparsers: argparse._SubParsersAction) -> None:
    movies = subparsers.add_parser("movies", help="Import, enrich, analyze, and recommend from your watched movies")
    commands = movies.add_subparsers(dest="movies_command", required=True)

    default_source = os.environ.get("TMDB_WATCHED_FILE", "~/Downloads/Watched Movies.xlsx")

    bootstrap = commands.add_parser("bootstrap", help="Import the workbook, match/enrich with TMDB, and print a report")
    bootstrap.add_argument("--source", default=default_source)
    bootstrap.add_argument("--limit", type=int, default=None, help="Process only the first N watched rows")
    bootstrap.add_argument("--refresh", action="store_true", help="Refresh existing automatic matches and metadata")

    import_command = commands.add_parser("import", help="Import the watched XLSX without contacting TMDB")
    import_command.add_argument("--source", default=default_source)

    sync = commands.add_parser("sync", help="Match imported titles and cache TMDB metadata")
    sync.add_argument("--limit", type=int, default=None, help="Process only the first N watched rows")
    sync.add_argument("--refresh", action="store_true", help="Refresh existing automatic matches and metadata")

    commands.add_parser("status", help="Show Movie Lab import, match, and catalog counts")
    commands.add_parser("review", help="Show ambiguous matches that need an operator choice")
    commands.add_parser("report", help="Analyze ratings and enriched genre performance")

    resolve = commands.add_parser("resolve", help="Resolve one ambiguous workbook row to a TMDB identity")
    resolve.add_argument("--row", type=int, required=True, help="Original XLSX row number")
    resolve.add_argument("--tmdb-id", type=int, required=True)
    resolve.add_argument("--media-type", choices=("movie", "tv"), required=True)

    recommend = commands.add_parser("recommend", help="Generate familiar and step-outside-your-box recommendations")
    recommend.add_argument("--limit", type=int, default=20)
    recommend.add_argument("--explore", type=float, default=0.25, help="Exploration share from 0.0 to 1.0")


def run_movies_command(args: argparse.Namespace) -> None:
    service = MovieLabService(MovieLabStore(default_movies_dir() / "movie-lab.json"))
    command = args.movies_command
    if command == "bootstrap":
        imported = service.import_workbook(Path(args.source))
        synced = service.sync_tmdb(limit=args.limit, refresh=bool(args.refresh))
        _print({"import": imported, "sync": synced, "status": service.status(), "report": service.report()})
        return
    if command == "import":
        _print(service.import_workbook(Path(args.source)))
        return
    if command == "sync":
        _print(service.sync_tmdb(limit=args.limit, refresh=bool(args.refresh)))
        return
    if command == "status":
        _print(service.status())
        return
    if command == "review":
        _print({"needsReview": service.review_queue()})
        return
    if command == "report":
        _print(service.report())
        return
    if command == "resolve":
        _print(service.resolve_match(source_row=args.row, media_type=args.media_type, tmdb_id=args.tmdb_id))
        return
    if command == "recommend":
        _print({"recommendations": service.recommend(limit=args.limit, exploration_share=args.explore)})
        return
    raise SystemExit(f"Unknown movies command: {command}")


def _print(payload: object) -> None:
    print(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True))
