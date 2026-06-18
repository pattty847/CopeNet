# CopeNet Roadmap / Backlog

Living backlog. Captures direction set by Patrick (idea-man) so nothing gets lost
between sessions. Order is a recommendation, not a contract — "whatever order's best."

Authoritative for *what shipped* is git log; this is for *what's next + why*.

---

## ✅ Recently shipped (context)

- NASA Astronomy Picture of the Day — Phase 1 (store + RPC + Home `ApodCard`), wired
  end to end, live on Home. Plan: `docs/plans/NASA_APOD_FEATURE.md`.
- `copenet help` — self-describing CLI guide (auto-lists commands from the parser).
- Mobile fixes: Workspace Files now folder-grouped + filename-first (overflow bug fixed);
  Persona "Loaded files" now filename-first with relative-path subtext.
- NASA APOD image caching — image bytes cached to `~/.copenet/sessions/nasa-apod-images/`
  and served via `GET /nasa/apod/image/{date}` (lazy + eager warm); card falls back to
  NASA on a cache miss. No more broken card when apod.nasa.gov 503s.

---

## 🟢 Now — Inspector pane cleanup (the real desktop panel)

IMPORTANT: the live desktop "INSPECTOR" pane is **`components/agents/InspectorOverview.tsx`**
(rendered via `RightPanel overviewOnly` → `InspectorOverview`). The earlier audit read
`RightPanel.tsx` directly, which is mostly the mobile/draft path — NOT what Patrick sees.
Aim cleanup at `InspectorOverview.tsx`.

What Patrick confirmed seeing (screenshot): INSPECTOR · LAST RUN (Edited 7 / Read 3) ·
RUNTIME · WORKSPACE · IDENTITY + MEMORY · WORKSPACE INTELLIGENCE (stack/packages/recommended
checks) · DESTINATIONS · SESSION INFO.

1. **LAST RUN grouping — KEEP / lean into it.** Patrick loves it ("consolidates all the
   artifacts in the chat into one, see them at a quick scroll"). Design signal: this is the
   pattern to extend.
2. **Trim the IDENTITY + MEMORY placeholder** — brain icon + "Identity stays available in the
   background. Relevant memory appears here after a run uses it." Permanent filler today.
   Hide/collapse until memory actually populates it (honest-empty-states). Wires up for real
   in the Memory arc.
3. ~~**WORKSPACE INTELLIGENCE / Stack / Packages / Recommended checks**~~ ✅ CUT
   (`InspectorOverview.tsx`, 2026-06-18). Circle back later only if we make it *actionable*
   (clickable checks that actually run a session). The backend `workspace_intel` service +
   `runtimeContext.workspaceIntel` still exist — only the inert panel display was removed.
4. (from audit, still valid) **Enrich Session Info** — `Last run 3m ago · 2 artifacts · 0 errors`.

---

## 🔵 Theme: Inline File Editor

We have a **read-only** viewer today (no `workspace.writeFile` RPC). Build editing once,
reuse everywhere.

- New `workspace.writeFile` RPC (append-only-safe? no — real edit; guard with workspace
  scope + the existing edit-backup store so it's revertible).
- Editable surface reachable from:
  - Agents tab — the artifact/tool **popout drawer** is `components/runtime/InspectorDrawer.tsx`
    (createPortal drawer, opens on artifact/Read-More click). The editor mounts here.
  - **Persona Home** — edit the loaded persona files (SOUL.md, IDENTITY.md, USER.md, …) in place.
- Library decision (Patrick asked): lean **textarea-based editor for v1** — zero new deps,
  ships fast, fine for plain unformatted markdown; bundle is already 1.2MB so keep it lean.
  Upgrade to **CodeMirror 6** later only if we want line numbers / find / soft-wrap / syntax.
  (Monaco is overkill — megabytes.)

---

## 🔵 Theme: Personas (next big arc)

Make persona files first-class and user-managed.

- **Two scopes:**
  - **Root / global** personas → stored in `~/.copenet` (user-level, cross-project).
  - **Project** personas → stored in the project (repo-local).
- **Persona picker** — a button (right panel + Persona Home) to choose/add a persona.
- Click to add root or project personas into the active runtime.
- Hooking the picker up to the runtime is part of this journey.

---

## 🔵 Theme: Memory (after Personas — mirrors the same model)

- **Two scopes**, same as personas: **global/root** (`~/.copenet`) and **project** (repo-local).
- **Model-initiated memory:** the model can be told "remember this."
  - If the user didn't say **where** (global vs project) → **ask**.
  - Then create a **draft** memory → user **approves or edits** before it's committed.
- Reuse the editor surface for the approve/edit step.

---

## 🟣 Content-format philosophy (applies to personas + memory)

- Default to **plain markdown text files**. Open to other formats but text is likely best.
- The **model maintains them** (when allowed) — keep them updated.
- Make them **clear, straight to the point, token-minimal but not at the expense of detail.**
- Human-readable + inspectable so continuity feels grounded, not spooky.

---

## 🐛 Investigation: parallel "batch" tool calls

- Harness sends `parallel_tool_calls=True` (`core/harness/tool_loop.py:377`), letting a model
  emit e.g. `write` + `read` + `edit` on the same file in one batch.
- **Concern (Patrick):** if executed concurrently, `edit` could race `read`/`write` on the
  same file — and logically `edit` depends on having read. Observed in the batch-tool UI.
- **To do:** trace whether same-batch tool calls run concurrently or are serialized; if
  concurrent, decide whether to serialize same-file writes (or sequence read→edit deps).

---

## 🟡 From the tab audit (medium-value, backend data exists)

- **Paused-run timeline** in the right panel — breadcrumb (started → tool ok → *awaiting you*)
  for context when a run is paused on an approval.
- **Observability:** replace the low-value "Provider Distribution" chart with a
  **policy-decision breakdown** (allowed / blocked / approval-required) — `RunStep.policyDecision`.
- Surface **session context** (unresolved questions / constraints) from `SessionStateRecord`.

---

## 🔭 NASA APOD — later phases

- Phase 2: Data & Tools "NASA" page (featured image + slider of collected days).
- Phase 3: `@NASA-IMOD` composer mention pipeline (capability-aware injection).
- ~~Hardening: cache the APOD image bytes~~ ✅ shipped (see Recently shipped).
