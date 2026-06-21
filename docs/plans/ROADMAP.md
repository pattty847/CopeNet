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
- ✅ **Persona Home** — pencil on each loaded file opens the same FileEditor inline.
  `persona.readFile` / `persona.writeFile` scoped to the persona root; revertible. Verified.
- ⬜ **InspectorDrawer artifact popout** — mount FileEditor for artifact/Read-More editing
  (`components/runtime/InspectorDrawer.tsx`). Artifacts are a different data path than
  workspace files — settle where an edited artifact writes back.

---

## 🔵 Theme: Personas (in progress)

Make persona files first-class and user-managed.

- ✅ **Brick 1 — picker (list / create / switch).** `persona.list` / `persona.create` +
  a Personas picker card in Persona Home (chips, active-first, "+ New" create). Selecting
  sets `default_persona_id`. Personas carry a `scope` field ("global" for now). Verified.
- ✅ **Brick 1.5 — `persona.author` model tool (first "AI builds your stuff").** Ask in chat
  and the model authors a persona itself. Model-facing tool whose description is the schematic
  (soul/identity/agents/user/tools/public_memory); `PersonaHomeService.author_persona` writes
  the sections; `persona_service` threaded into the tool context. Authored personas show in
  the picker + are editable inline. Verified deterministically; ready for a live chat test.
- ✅ **Brick 2a — storage relocation.** Personas now live at the canonical
  `~/.copenet/personas` (or `COPNET_DATA_DIR/personas`), never under `sessions/`. Patrick's
  data was migrated by hand (stale canonical dir backed up to `personas.stale-bak-*`; active
  data promoted from `sessions/personas`). 398 tests pass.
- ⬜ **Brick 2b — project scope.** `<project>/.copenet/personas` + scope-aware discovery,
  creation, and resolution (project-then-global precedence). Make PersonaHomeService
  multi-root; the `scope` DTO field + the "+ New" picker get a project option. Sessions
  still just *reference* a persona — no per-session persona folders.
- ⬜ **Per-model override reconciliation.** A saved per-model flavor override currently wins
  over `default_persona_id`, so switching the picker doesn't visibly change the *resolved*
  persona for a model that has an override. Decide: switching clears/sets the override, or
  the picker edits the override directly. (Surfaced by Brick 1's "Active persona" card.)
- ⬜ **Picker in the right panel too** (not just Persona Home), for in-session switching.

---

## 🟢 Theme: Mid-session runtime mutability (A + B1 shipped)

The "session locks to provider/model/profile/task after first send" invariant was a
product *policy*, not a data constraint — every run already stamps its own provider/model
in the transcript + run record, so switching stays auditable per-turn. Reframed: a session
is a container; each run picks its runtime; past runs never change.

- ✅ **Mobile approval fix** — the ApprovalRequestCard was trapped in the desktop-only
  right panel; off-allowlist Ask-mode prompts never reached mobile. Now rendered inline in
  the center column on mobile + the paused banner opens the mobile Inspector sheet.
- ✅ **A — change Access mid-session.** `assert_session_binding` reconciles `task_prompt_id`
  instead of raising. The model can't alter its own runtime (params come from the operator
  request); Full Access stays provider-gated. Editable in the locked runtime popover.
- ✅ **B1 — same-provider model switch mid-session.** Same reconcile path for `model`.
  Editable Model dropdown in the locked popover; applied as a pending override on next send.
- ⬜ **B2 — cross-provider switch.** Provider stays hard-locked today. Needs continuity
  care: some providers keep server-side session state, so a new provider gets the transcript
  *replayed* fresh. Confirm the replay/context-rebuild path is solid for every provider, then
  relax the provider lock too.
- ⬜ **B3 — multi-model orchestration** (north-star). Two+ models collaborating, roping in
  local models. A new feature class (sub-agents/orchestration), not a field unlock — its
  own design doc. The per-run-runtime + transcript-as-truth primitives from A/B1 are the
  substrate. See also the north-star section.
- ✅ **Live smoke test (DONE 2026-06-21, on-device mobile).** Ask mode → `whoami` paused and
  the approval card rendered inline in the chat on mobile; Approve ran it (exit 0,
  `policyDecision: "allowed"`); "Always allow" persisted to the global allowlist so the next
  two runs went straight through with no prompt. Full loop verified: prompt → approve →
  standing allowlist → silent. Root cause of the earlier no-popup was a stale tailnet process
  (pre-Brick-D code) + browser cache, not a code bug — resolved by restarting the tailnet host.

---

## 🔵 Theme: Access & Permissions (in progress)

Separate **permissions** (what a runtime can touch) from **behavior** (how it acts). Today
the "task mode" axis mashes them together — `planning/debug/code-review/refactor/none` are
pure prompt presets; only `full-access` actually changes policy. So:

- **Behavior → Profiles**, **Access → a small permission axis** (rename the "Mode" selector).
  Proposed values: **Read-only · Ask · Full Access**. Suggested label: **"Access"**.
- Builds on what already exists: the approval-gated executor (run pauses on
  `approval_required`), the ApprovalRequestCard, the shell allowlist, and per-call approvals.

What CopeNet already has: 6 task modes; an approval pause/resume flow + card; a static shell
allowlist; per-run memory of approved commands. The bricks below add the rest.

- ✅ **A — read-allowlist band-aid.** Added `cat/tail/wc/tree/file/which/diff` to the default
  shell allowlist so common reads stop being silently blocked (the `cat` bug). Verified.
- ✅ **B — persist last Access level.** The draft now persists `taskPromptId` so the chosen
  Access sticks across provider/model switches + reload (was resetting to `none`). Verified.
- ✅ **C — "Access" selector.** Done:
  - ✅ **Backend Full-Access gate**: `policy_for_task_mode(provider=…)` downgrades full-access
    to read-only for non-Claude/OpenAI providers. Enforced regardless of UI.
  - ✅ UI: Full Access option hidden for non-Claude/OpenAI providers (`lib/access.ts`,
    single source of truth, consumed by AgentComposer + RightPanel). A draft holding
    `full-access` is coerced to Read-only when the provider can't grant it.
  - ✅ Renamed Mode → Access. Values shipped: **Read-only / Full Access** (Ask is Brick D —
    deliberately not shipped as a dead option).
  - ✅ Moved behavioral presets (planning/debug/code-review/refactor) into Profiles by
    relocating the preset `.md` files. `taskPromptId` field kept; old locked sessions
    degrade gracefully (overlay drops, policy unchanged).
  - ⬜ **Follow-up:** `MessagingSettingsPanel.tsx` still renders a backend-enumerated "Task
    mode" dropdown — now naturally reduced to `none`/`full-access`. Convert it to the same
    Access control (`accessOptionsFor`) for consistency when that panel is next touched.
- ✅ **D — "Ask" mode.** Third Access value shipped. Off-allowlist shell commands return
  `approval_required` (operator prompt) instead of silently blocking, reusing the existing
  pause/resume/approve flow; on approve the command re-runs with full shell, on reject the
  model adapts. `prompt_on_block` flag in `policy.py` (ungated — operator is the gate),
  block→prompt conversion in `handlers/shell.py`, `ask.md` preset, `lib/access.ts` ladder
  entry. 5 new shell tests; read-only path byte-for-byte unchanged. Verified in-browser.
- ✅ **E — "Always allow" → global persisted allowlist.** `core/permissions/PermissionStore`
  (in-memory + atomic JSON at `~/.copenet/sessions/permissions.json`, whitespace-normalized,
  global over per-session). `decide_approval` accepts `approved_always`; the gated executor
  persists on it. `handlers/shell.py` consults a standing-approval set (run-scoped ∪ global)
  and runs matches with full shell in any Access mode. ApprovalRequestCard got an "Always
  allow" button. Threaded onto `ToolExecutionContext.permission_store`. 9 tests.
- ✅ **F — Permissions settings UI.** `permissions.allowlist.list/add/remove` RPCs (new
  `rpc_permissions.py`), wsClient wrappers, and a `PermissionsSettingsPanel` mounted as a
  new "Permissions" route under Data & Tools (view/add/remove entries). Verified end-to-end
  in-browser. Default-Access-level setting was effectively delivered by Brick B (the draft
  persists the last-selected Access), so it's not re-litigated here.

**Theme complete (A–F).** Remaining adjacents are nice-to-haves, not blockers: the
MessagingSettingsPanel task-mode dropdown could adopt `accessOptionsFor` (noted under C),
and a fresh README screenshot of the Permissions surface per the UI-polish convention.

---

## 🟢 Theme: Memory (in progress — evolve the existing store, don't rebuild)

**Grounding decision (2026-06-21):** memory ALREADY exists as a solid JSON store —
`core/memory/` (`MemoryStore` + `MemoryService`), with **relevance ranking already built**
(`select_relevant`: term-overlap + category bonus, top-3 for tool runs / top-1 for text),
injection via `_build_identity_memory_overlay` (runtime.py), RPCs (list/upsert/archive), a
`memory.changed` event, and a `MemorySurface` UI. The "don't dump poo on the porch" concern
is therefore **already solved**. So we EVOLVE this store rather than rebuild it as markdown
files — the markdown-vs-JSON detail isn't the value; the value is the *AI-proposes →
you-approve* loop + scopes, which is storage-agnostic. (Pure-markdown storage stays a
possible later migration, not a prerequisite.)

What's actually missing (the build, mirroring the Personas `persona.author` pattern):
- ⬜ **M1 — `memory.remember` model tool + draft→approve.** The model proposes a memory
  (category/title/summary/detail/tags) but it lands as a **draft** (`status="draft"`),
  NOT committed. Operator approves / edits / discards from the Memory UI. Drafts are
  excluded from relevance injection + the default list. Mirrors persona.author but
  draft-first. `memory_service` is already on `ToolExecutionContext`.
- ⬜ **M2 — scope (global vs project).** Add a `scope` field; project memory under
  `<workspace_root>/.copenet/memory.json` (session_workspace_root is on the context). If the
  model didn't say where, the approve step asks. (Global-only is fine for M1; add scope next.)
- ⬜ **M3 — approve/edit surface** in `MemorySurface`: a "pending review" section with
  Approve / Edit / Discard; Edit reuses the existing memory form.

---

## 🟣 Theme: Stock Watcher — the first heartbeat (parked, post-Memory)

Patrick's one genuine "runs while I'm away" idea, and the ideal first heartbeat: weekday
after-close cadence, free daily data (yfinance), read-only-safe, produces a "what I found
while you were away" briefing artifact. **Honest framing:** not an alpha machine (edge gets
arbitraged) — an **attention machine** that scans a universe so Patrick doesn't have to, and
surfaces a short list for his judgment. Daily/monthly bars are the *correct* timeframe for
the swing use case (intraday only matters for day-trading, which isn't the goal), so the
"no free intraday" worry is a non-issue.

Signal design (Patrick's):
- **Ehlers MAMA/FAMA (MESA Adaptive MA) crossovers** on a long-term **monthly** swing basis.
- Track the **% distance between MAMA and FAMA** to infer an *impending* crossover from
  sideways/compression after a long trend (the adaptive lines compressing = setup forming).
- Plus a **reversal/momentum** indicator and a **headline/news jumpstarter** for context.
- **Universe scan** → spot opportunities; a second model angle hunts **long-term value**.
- Aspiration: a real **alpha generator** (acknowledged hard; willing to try — "why not").

Convergence: this is the first real consumer of **Memory** (watchlist, indicator thresholds,
risk prefs) and the **heartbeat** that finally makes the return **briefing** substantive. Good
candidate to dogfood **GPT-5.5-in-CopeNet** on the *greenfield indicator module* (low blast
radius, obviously verifiable) while **Codex** takes the wsClient/orchestrator refactor.

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

## 🟣 Parked: mobile density / spacing pass (own brainstorm session)

Patrick's observation: on mobile there's too much padding on objects (e.g. the left
gutter eats horizontal space). Wants a deliberate pass across ALL mobile objects to
reclaim space — not a one-off tweak. Gets its own planning/brainstorm session before
implementation. Touches the global shell padding/gutters, so scope it carefully.

## 🟡 From the tab audit (medium-value, backend data exists)

- **Paused-run timeline** in the right panel — breadcrumb (started → tool ok → *awaiting you*)
  for context when a run is paused on an approval.
- **Observability:** replace the low-value "Provider Distribution" chart with a
  **policy-decision breakdown** (allowed / blocked / approval-required) — `RunStep.policyDecision`.
- Surface **session context** (unresolved questions / constraints) from `SessionStateRecord`.

---

## 🌌 North-star vision (Patrick) — directional, not yet scoped

CopeNet is becoming the "everything app." Directional bets to keep in view:

- **Domain workspaces** — first-class OSINT and Cybersecurity workspaces (curated tools,
  data sources, layouts, prompts per domain). The persona/memory/editor primitives we're
  building are the substrate for these.
- **AI-built workspaces** — the agent builds the user a custom workspace from a described
  intent ("I want an OSINT workspace for X"): assembles the right tools, data sources,
  persona, and memory scaffolding. The editor + personas + memory arcs are prerequisites;
  this is the payoff that ties them together.

## 🔭 NASA APOD — later phases

- Phase 2: Data & Tools "NASA" page (featured image + slider of collected days).
- Phase 3: `@NASA-IMOD` composer mention pipeline (capability-aware injection).
- ~~Hardening: cache the APOD image bytes~~ ✅ shipped (see Recently shipped).
