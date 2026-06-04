# Frontend roadmap — mock vs wired audit + build order

From a parallel-agent audit of the whole frontend (2026-06). Goal: build toward
"our own Codex / Claude Code" — **live incremental updates that collapse into clean
historical breadcrumbs**, balanced for vibe-coders, backed by **deeply inspectable
formats (a mini-IDE: line numbers, syntax, even editable)** so the user never opens a
separate editor to trust the model's work.

## State of the frontend

More real than it looks. **Wired to live RPCs:** the whole Agents console, Observability,
Inspector, messaging config + routes, all approval *display* surfaces, inline tool/diff
rendering. The mock layer is small and concentrated in three vision-critical places:

1. **Diff inspectability** — diffs were read-only flat +/- lines. *(line-number gutters
   shipped `6dcba66`; syntax highlighting + apply/reject still open.)*
2. **Live→history collapse seam** — half-built: `LiveToolFeed` has dead code where a
   `RunActivityPanel` should take over; `activityProof.ts`'s `useRunActivity` mapper
   exists but nothing renders it.
3. **Operator actions are mock** — approval approve/reject and message-send route through
   `useMockTransitions.simulate*` (client-side fabrication), not real RPCs.

## Build order (by leverage vs effort)

| # | Item | Effort | Backend dep | Status |
|---|------|--------|-------------|--------|
| 1 | Diff line-number gutters | M | none | ✅ shipped `6dcba66` |
| 1b | Diff + read-preview syntax highlighting | M | none | ✅ shipped `084ebc6` (visual pass pending) |
| 2 | Wire approval/send actions to real RPCs (kill `simulate*`) | M | `resolveApproval` + `messaging.send` RPC | open |
| 3 | Diff Keep/Revert affordance (inline buttons) | L | `sessions.revertEdit` RPC | ✅ shipped `0d396e0` (revert = undo applied edit; backend store + RPC built) |
| 4 | `RunActivityPanel` — complete the live→history collapse seam | M | none (uses `SessionRunRecord.toolSteps`) | ✅ shipped `b297ff5` |
| 5 | Per-tool live event stream (queued/running chips in `LiveToolFeed`) | M | `tool:called`/`tool:result` deltas | open |
| 6 | Line numbers + syntax on read previews (`FileReadPreviewBlock`) | M | none | ✅ shipped `084ebc6` (folded into 1b) |
| 7 | Wire `ReturnBriefing` to real data (drop `DEV_SKELETON_FOR_TEST`) | S | `briefing:ready` push | open |

**No-backend wins (drive these solo):** 1 ✅, 1b, 4, 6.
**Need backend (I own these now too):** 2, 3, 5, 7 — 2 & 3 build on `docs/plans/APPROVAL_FLOW.md`.

## Notable mock/scaffold findings

- **The "diff accept popup / right-menu" the owner remembered does NOT exist** — named in
  the catalog, no code. Item 3 is where it lands (build inline Accept/Reject buttons
  first; the right-click context menu is a later flourish).
- **`DiffArtifactView`** (patch_plan artifacts) renders a literal dashed
  *"Apply and reject will wire to the runtime patch API when it lands"* placeholder
  (`DiffArtifactView.tsx:111-115`). Item 3 wires it.
- **`useMockTransitions`** (`adapter.ts:332-431`) is the single biggest pure-mock block:
  `simulateApprove/Reject/Modify` + `simulateSendMessageComposed`. Item 2 deletes it.
- **`ReturnBriefing`** is a complete UI on `DEV_SKELETON_FOR_TEST` hardcoded data —
  the "I'm back" continuity surface, waiting on a `briefing:ready` backend push.
- **Experiments page** future-probe cards (Prompt Face-Off, Tool-Use Compliance, Latency
  Leaderboard) are intentional directional mockups per AGENTS.md — leave as shells.
- `runtime/mocks.ts` is a deliberate fallback (every adapter hook tries backend first,
  falls back to mock) — don't delete; it keeps the UI honest before backend lands.

## Parallel track (not UI): agentic capability tests

Owner also wants an eval harness that makes the model **build projects, create/edit/run
files, act like Claude Code** end to end — proving the model can do the work, not just
render it nicely. Natural complement to the mini-IDE UI: the UI makes the work
inspectable; the eval proves the work happens. Scope TBD — likely task scenarios scored
on whether files were correctly created/edited/run in a full-access scratch workspace.
