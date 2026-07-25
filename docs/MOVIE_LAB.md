# Movie Lab

Movie Lab turns a personal watched-movies workbook into a local, TMDB-enriched
taste dataset. The workbook remains source material; CopeNet never edits it.

## Local setup

Put one TMDB credential in the ignored `.env.local` file:

```text
TMDB_ACCESS_TOKEN=your_api_read_access_token
```

The optional source override is `TMDB_WATCHED_FILE`. Without it, the CLI reads
`~/Downloads/Watched Movies.xlsx`.

Movie Lab data is stored atomically at
`COPNET_DATA_DIR/movies/movie-lab.json`, or `~/.copenet/movies/movie-lab.json`
when `COPNET_DATA_DIR` is unset. Credentials are never written to that store.

## Workflow

```bash
# Import the workbook without making a network request.
uv run copenet movies import

# Match titles and cache TMDB genres, keywords, credits, and core metadata.
uv run copenet movies sync

# Inspect matches that cannot be selected safely without a year/media choice.
uv run copenet movies review

# Resolve one reviewed row using an id shown in the review candidates.
uv run copenet movies resolve --row 31 --media-type movie --tmdb-id 306947

# Analyze personal ratings and enriched genre performance.
uv run copenet movies report

# Generate a quality-filtered slate with a 30% exploration target.
uv run copenet movies recommend --limit 20 --explore 0.30
```

`uv run copenet movies bootstrap` combines import, sync, status, and report for
a fresh setup.

## Matching rules

Matching is deliberately conservative:

- TMDB multi-search handles movie and TV records.
- Exact titles, explicit TV hints, vote evidence, and a small visible alias map
  resolve canonical entries.
- Plausible remakes or same-name media remain in the review queue.
- Manual resolutions survive normal syncs and are refreshed only when requested.
- Incomplete component ratings are stored with `finalScore: null`; spreadsheet
  formula zeroes are not interpreted as real zero-star ratings.

## Recommendation lanes

The first engine uses the highest-rated matched entries as seeds, merges TMDB
recommendation candidates, removes already-watched items, applies minimum vote
and rating evidence, and labels each result as either:

- `inside your lane`: familiar genre connections to highly rated watches;
- `step outside your box`: a recommendation connected to a strong seed that
  also includes genres that are still underexplored in the watched history.

The stored explanation includes seed titles and the scoring evidence so a future
UI can show why each recommendation exists rather than presenting a black box.

## Next product surface

The local JSON contract is ready for an RPC and React visualization layer. The
first useful views are a taste fingerprint, genre-by-score heatmap, initial vs.
final rating scatterplot, match-review queue, and two-lane recommendation board.

TMDB attribution must be included in any UI that displays TMDB data or images.
