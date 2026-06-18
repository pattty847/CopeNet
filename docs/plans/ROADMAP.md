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
- Inline file editor keystone (`workspace.writeFile` + `FileEditor` in WorkspaceFileViewer)
  — see the Inline File Editor theme below for what's shipped vs. pending.
- WORKSPACE INTELLIGENCE section cut from the inspector overview.
- Committed on branch `feat/apod-cli-mobile-inspector-editor` (8 commits).

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

KEYSTONE — partially shipped 2026-06-18.

- ✅ **`workspace.writeFile` RPC** — guarded operator write (root-scoped, text-only, 1MB cap,
  atomic), records a pre-edit backup so it's revertible via the existing `sessions.revertEdit`.
- ✅ **`FileEditor.tsx`** — reusable, no-library plain `<textarea>` (dirty tracking, Cmd/Ctrl+S,
  Save/Cancel). Decision settled: roll our own, textarea-based; CodeMirror only if we ever
  outgrow plain text.
- ✅ **WorkspaceFileViewer** — Edit button on an open file; save round-trips + refreshes.
  Verified end to end in the browser (disk persist + revert backup + traversal blocked).
- ⬜ **Persona Home** — reuse FileEditor to edit loaded persona files in place. Needs a
  persona-root-scoped write RPC (persona files live under ~/.copenet, NOT a session
  workspace root, so `workspace.writeFile` can't reach them).
- ⬜ **InspectorDrawer artifact popout** — mount FileEditor for artifact/Read-More editing
  (`components/runtime/InspectorDrawer.tsx`). Artifacts are a different data path than
  workspace files — settle where an edited artifact writes back.

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
