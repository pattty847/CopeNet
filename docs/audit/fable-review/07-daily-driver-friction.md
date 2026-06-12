# Daily-Driver Friction

What breaks, annoys, or is missing if you start living in this tomorrow. Ordered by daily-use impact.

## Blockers

### No way to stop a run
`wsClient.abortActiveRun()` (`wsClient.ts:2047`) has zero callers; no stop/abort control exists in `AgentComposer.tsx` or `ChatWorkspace.tsx` (the only "Cancel" is a dialog cancel). The backend is fully ready (`chat.abort` → `rpc_chat.py:196` → `orchestrator/__init__.py:159-170`). A run that's looping through tools or stuck on openai-codex (180s HTTP timeout per request, multiplied by a multi-step tool loop) cannot be interrupted — you wait or kill the server. **Fix:** Stop button in the composer when `activeRunId` is set.

### A crash mid-run permanently bricks the session
Stale `in_flight_run_id` survives a process kill, no startup sweep exists, and `chat.abort` can't clear it after restart (`orchestrator/__init__.py:161-167` returns `aborted: false`). Every send to that session errors forever; the fix is hand-editing `index.json`. Rare trigger, fatal outcome, invisible cause. Full analysis in `05-session-invariants.md` findings 1–2.

### Fresh clone silently serves the old legacy UI
`frontend/dist/` is gitignored; the host silently falls back to `static/index.html` — the vanilla legacy UI — when dist is missing (`api.py:23-24`). Neither README's Quickstart nor `docs/STARTUP.md` ever mentions `npm install && npm run build`; the build steps live only in `frontend/README.md`, which nothing points to. On a new machine the documented steps produce a UI that looks nothing like the screenshots, with no hint why. **Fix:** document the build step and log a loud "serving legacy fallback UI" warning in `create_app()`.

### Per-connection event emission breaks reconnect, approvals, and the second device
Chat/approval events are emitted through the originating socket's `send_json` closure (`rpc_chat.py:122-133`, exceptions swallowed); `ws_server.py` has no connection registry or broadcast (one socket per `handle()`). Consequences:
- **WiFi blip / laptop sleep mid-run:** the new socket has no link to the running task. `reconcilePendingRuns` (`wsClient.ts:1382-1411`) marks the message `reconnecting: true` with a comment claiming "events resume" — they cannot. The completed answer exists in the transcript but only appears after switching sessions or reloading.
- **Approvals die on reload:** approvals arrive only via the connection-bound `approval.pending` push; bootstrap fetches 14 RPCs but nothing approval-related (no `approval.list` RPC exists). Reload during an approval → the card is gone, the run times out at 300s (`orchestrator/__init__.py:666`). Also: any approval older than 5 minutes is dead on arrival — directly at odds with the "walk away and come back" product vision.
- **Tailnet phone:** README sells multi-device (`README.md:104-110`, `COPNET_HOST=tailscale` in `main.py:24-29`), but a run started on the desktop is invisible on the phone until manual reload. Mobile Safari backgrounding drops the socket constantly, so mobile is hit hardest.

**Fix (one root cause):** a connection registry in `CopeNetWsServer` with session-scoped broadcast, plus an `approval.list`-style RPC fetched at bootstrap.

## Annoyances

### Setting a real `COPNET_TOKEN` — as the docs recommend — locks the browser out
`docs/STARTUP.md:58` recommends a real token before tailnet exposure. The frontend resolves its token from build-time env / window global / localStorage / meta tag, then falls back to hard-coded `'dev-token'` (`wsClient.ts:75-80`) — and **no UI exists to enter a token** (nothing ever calls `localStorage.setItem('copnet.token', ...)`). Following the hardening doc yields a permanent auth-failed banner; the workaround is devtools. **Fix:** token prompt on `auth_failed` that persists to localStorage.

### Provider auth: solid mid-run, contradicted by the UI
Refresh is automatic and proactive (`provider_auth/openai_codex.py:152-164`, called at the start of every request, `providers/openai_codex.py:87,152`), and hard 401s produce an actionable inline error. But `status()` computes `expired` as raw `expires_at <= now` (`provider_auth/openai_codex.py:55`) without considering refreshability — so after any idle period the ProviderAuthCard shows amber "Token Expired" + "Log in to Codex" even though the next send self-heals. Plus the known missing `provider:auth:updated` push means a manual Refresh after every login. Recurring false alarm. **Fix:** report "auto-refreshes on next use"; push auth status after completeLogin.

### Workspace root silently defaults to wherever you launched the process
`orchestrator/__init__.py:113-115`: `COPNET_WORKDIR` or `os.getcwd()`. The env var is documented nowhere in README/STARTUP. Launch from a different directory and full-access file/shell tools operate somewhere else with no UI callout of why. **Fix:** document `COPNET_WORKDIR`; surface the effective root prominently at draft time.

### Cold start with zero providers has no onboarding path
`pickPreferredProvider` falls back to `'codex-cli'` even when nothing is available (`wsClient.ts:84-89`); no "no providers connected" empty state exists anywhere in `components/`. A new user sees normal dropdowns, sends, and gets a failure — the only auth surface is the ProviderAuthCard buried in the right panel's runtime tab, openai-codex only. **Fix:** honest zero-provider state on Home and in the draft drawer with setup pointers.

### Stale docs
`docs/STARTUP.md:76` documents `uv run copenet-host` — the script doesn't exist (`pyproject.toml` defines only `copenet` and `copenet-browser-demo`). CLAUDE.md's gaps table is 4/7 stale (see `02-unfinished-contracts.md`).

## Cosmetic

- **`durationMs` always 0** in activity surfaces (`activityProof.ts:26,80`; backend emits no duration) — the tool timeline can't answer "what was slow," which starts to matter once you watch runs daily.
- **Hard-coded hub copy:** WorkflowsPage hero "Workbench State: Live 1 / Drafting 2" is static text (`WorkflowsPage.tsx:40-45`).

## Nav-section reality check

| Section | Verdict | Evidence |
|---|---|---|
| Home | PARTIAL | Mission Control is live (`HomePage.tsx:60-66` fans `sessions.runs` + `sessions.resolve` across sessions); Return Briefing is an honest skeleton with a dev preview button (`HomePage.tsx:142-157`). |
| Agents | REAL | Full RPC surface: chat send/abort/history, sessions.*, models, approvals, workspace files. |
| Workflows | PARTIAL | Meme Lab is real (`memeClient.ts:265,352` → `/api/v1/memes/*`); hub framing is static copy. |
| Data & Tools | PARTIAL | Media import/extract is real REST; the rest of the 1,106-line page is direction-setting copy. |
| Observability | PARTIAL | One real source (`sessions.runs` per session, `ObservabilityPage.tsx:60,87`); no trace-file surface despite the tracing subsystem existing — a missed easy win. |
| Experiments | PARTIAL | Single backend call (`listSessionRuns`); ~400 lines of framing. |

## Mobile — genuinely real (positive)

Width-based activation <1024px (`lib/responsive.ts:3-8`), dedicated bottom nav + top bar with a live WS status pill (`mobile/MobileNav.tsx:28-123`), sessions/inspector as sheets, safe-area insets, and deliberate insecure-origin support for plain-http tailnet Safari (`safeUUID` fallback, `wsClient.ts:91-100`). A working layout, not a shell. Its one real problem is inherited: the per-connection push issue above, which hits backgrounded mobile Safari hardest — fixing broadcast is what makes mobile actually pleasant.
