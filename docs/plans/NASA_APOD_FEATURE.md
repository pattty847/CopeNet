# NASA APOD Feature Plan

**Status:** approved, not yet started (awaiting go on Phase 1)
**Owner:** Claude
**Director:** Patrick

## Vision

NASA Astronomy Picture of the Day as an ambient + explorable surface in CopeNet —
"orient you to our place in the universe when you walk back." Three surfaces over one
persisted collection, plus a reusable `@`-mention pipeline that NASA seeds.

## Assets already in place

- `NASA_API_KEY` in `.env` (server-side) — do NOT ship to browser.
- `docs/apis/NASA-api-docs.json` — swagger for all 16 NASA APIs (APOD + NeoWs, DONKI,
  EONET, EPIC, Exoplanet, NASA Image/Video Library, etc.). Future expansion lives here.
- APOD endpoint: `GET https://api.nasa.gov/planetary/apod?api_key=…&date=YYYY-MM-DD&hd=true`
  → `{title, explanation, url, hdurl, media_type, date, copyright}`.
  `media_type` may be `"video"` — must handle (embed/link, not `<img>`).

## Decisions (locked)

- **@ resolution = capability-aware.** Always inject title + explanation as text; ALSO
  attach the image only when the model is vision-capable (use harness capability profile).
  Text-only CLI / LM-Studio / Ollama models get text + URL, no image attachment.
- **Phasing = foundation-first.** Each phase independently mergeable + verifiable.

## Phase 1 — Foundation (store + RPC + Home widget)

- New `core/nasa/` store: append-only, date-keyed APOD collection (mirror `pulse`/`memory`
  operator-store pattern; atomic temp-file + rename writes).
- Backend fetch fn reads `NASA_API_KEY`, fetches APOD, normalizes, persists to store.
  Reusable later as both the page data source and the @-mention resolver source.
- Server-side day cache so Home mount doesn't re-hit NASA repeatedly.
- RPC: `nasa.apod` (today) + `nasa.apod.list` (collection). Add + verify RPC first.
- Frontend `ApodCard` on Home. Honest states: loading skeleton, video media_type,
  error / missing-key empty state (no phantom data). Click → routes to Data & Tools NASA page.

## Phase 2 — Data & Tools "NASA" page

- New page under Data & Tools section (existing nav — no new top-level nav needed).
- Large featured image up top; horizontal slider of collected APODs below.
- Click a thumb → it becomes featured. Title / date / copyright / collapsible explanation.
- Reads `nasa.apod.list` from the Phase 1 store.

## Phase 3 — @-mention pipeline (`@NASA-IMOD`)

- New reusable composer mention-resolver + registry. NASA is the FIRST provider, not a
  one-off. Registry maps `@<id>` → a resolver that returns context-injectable content.
- `@NASA-IMOD` resolver pulls today's (or a chosen date's) APOD from the store.
- Capability-aware injection wired through harness capability profile.
- Composer: `@` triggers an autocomplete of registered mentionable resources.

## Backend contracts this introduces

- `nasa.apod` RPC → normalized APOD record for a date (default today).
- `nasa.apod.list` RPC → collection (paginated/limited).
- Mention-resolver contract (Phase 3): `@<id>` → `{ text, attachments?: image[] }`,
  filtered by model capability at injection time.
