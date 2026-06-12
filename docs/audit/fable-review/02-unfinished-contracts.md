# Unfinished Contracts

Places where one side of the system is wired to something the other side doesn't implement.

## CLAUDE.md "Backend Gaps" table — line-by-line verification (4 of 7 rows stale)

| Claimed gap | Verdict | Evidence |
|---|---|---|
| `durationMs` on `RunStep` always 0 | **STILL REAL** (location stale) | `mapToolStep` moved to `runtime/activityProof.ts:26,80`, both hardcode `durationMs: 0`. Backend `_normalize_tool_step` (`runtime.py:988-1027`) emits no duration field. |
| `provider:auth:updated` push missing | **STILL REAL** | Absent from the server events list (`ws_server.py:199`); no client handler; `ProviderAuthCard.tsx:18-20` still documents manual Refresh. |
| Pat Profile RPC missing | **FIXED** | `profile.get` dispatched (`rpc_dispatch.py:132` → `rpc_catalog.py:95-104`); fetched in bootstrap (`wsClient.ts:1311`), `setPatProfile` called at `:1333`. |
| Return Briefing RPC missing | **FIXED** | `briefing.get` (`rpc_dispatch.py:150` → `rpc_catalog.py:252-261`); bootstrap fetch `wsClient.ts:1317`, `setReturnBriefing` at `:1349`. |
| `profile:loaded` push never sent | **FIXED (superseded)** | Replaced by bootstrap pull; `setPatProfile` also fires on `profile.changed` (`wsClient.ts:1124`). |
| `profile:changed` push never sent | **PARTIALLY FIXED** | Backend emits at `runtime.py:668-674` and the client handles it — but emission requires `COPNET_AUTO_PROFILE_EXTRACTION=1` (default off, `_config.py:38-43`, gate at `runtime.py:633`). In a default install the event never fires. |
| `briefing:ready` push never sent | **FIXED** | Emitted after every run (`runtime.py:691-694`); handler `wsClient.ts:1148-1152`. |

**The table needs rewriting.** A developer trusting it would re-implement shipped RPCs.

## Critical: the message composer sends nothing

`SendMessageComposer.tsx:181,199` calls `simulateSendMessageComposed()` (`adapter.ts:399-428`), which fabricates the outbound record client-side. There is no `messaging.send` RPC in the dispatch table (`rpc_dispatch.py:112-234`) and no delivery function or Telegram HTTP client anywhere in `core/messaging/` or `core/orchestrator/messaging.py`. The full approve-to-send flow the composer spawns is theater, including a fabricated approval id that the real `chat.decideApproval` backend will reject. Either build the delivery lane or remove the composer until it exists.

## Pat Profile: the read path is real, the "learning" is a scripted demo

- **Real:** file-backed overlay storage with append-only `changelog.jsonl` (`profile/service.py:631-656`), and the profile genuinely reaches the model — `_build_identity_memory_overlay` (`runtime.py:1051-1075`) joins `build_identity_prompt_payload()` into the system overlay every run. The frontend gets it via `profile.get`.
- **Fake:** `apply_post_run_updates` (`profile/service.py:387-515`) — the only mutation logic is hardcoded keyword demos: `if "punchline" in lower:` (line 399), `if "china crypto ban" in lower and "ignore" in lower:` (line 433), `if "school" in lower and "crypto" in lower ...` (line 453), and a `_recent_keyword_count("crypto") >= 3` tendency (line 481). Gated off by default behind `COPNET_AUTO_PROFILE_EXTRACTION`.

The continuity-engine vision rests on this layer; today it's storage + injection with demo-script learning.

## Persona service: genuinely real end-to-end (positive)

`persona/service.py` — file-backed with atomic temp+rename writes (:46-50), privacy-tier-aware prompt assembly (`build_prompt_context` :206-264), per-model flavors persisted to disk. Injected into the system overlay every run (`runtime.py:1045-1049`); full RPC surface (`rpc_catalog.py:119-236`) fetched at bootstrap. No action needed.

## Multiagent delegation: floating

Complete, documented, tested — and `grep -rn "MultiAgentOrchestrator|delegate_subagent|execute_with_fallback|select_provider_chain" src/copenet` returns zero hits outside the package. No tool exposes it to the model; nothing in `orchestrator/` or `harness/` imports it; the role map references a nonexistent `gemini` provider (`provider_selector.py:50`). The contract for how it joins the live `send_chat` flow does not exist yet — that contract should be written before more multiagent code lands on top of it.

## Approval protocol: the frontend advertises a decision the backend rejects

`simulateModify` (`adapter.ts:385-393`) marks an approval `'modified'` in the local store and never calls the RPC. Backend `decide_approval` (`orchestrator/__init__.py:731`) accepts only `{"approved", "rejected"}` — a "modified" decision leaves the run parked until the 300s timeout while the UI shows it resolved. The `ApprovalOutcome` type and inbox label "Modified" advertise a capability the protocol doesn't have.

## RunTimeline: no producer on either side

Nothing populates the `runTimeline` store slice (only `setRunTimeline(null)` cleanup at `adapter.ts:492`); no backend event carries a timeline payload. The component (`RunTimeline.tsx`, mounted at `RightPanel.tsx:550`) renders its empty state forever — yet its approve/reject buttons call the real `decideApproval`.

## WS push-event parity: otherwise clean (positive)

Every event in `handleEventFrame` (`wsClient.ts:1101-1222`) has a verified backend emitter and vice versa: `chat`, `profile.changed`, `memory.changed`, `briefing.ready`, `sessions.merge.updated`, `pulse.updated`, `messaging.updated`, `approval.pending`, `approval.resolved`. The only missing push is provider-auth (above). Minor: the `messaging.updated` branch lacks a trailing `return` — harmless fallthrough today.

## RPC layer: real, with cosmetic drift

All 60+ methods in `rpc_dispatch.py:112-234` delegate to real implementations. Drift: `sessions.debugCopy`/`sessions.export` are dispatched and used but missing from the advertised method list (`ws_server.py:139-198`); `messaging.routes.resolve` is advertised but dead; `providerAuth.completeLogin` is intentionally uncalled by the browser (OAuth callback hits localhost:1455 directly).

## Caveat worth knowing: `harness_planned` can lie for Ollama

`_StreamingHttpProvider.describe()` claims `toolCalls: True` for both LM Studio and Ollama (`local_http.py:74`) while Ollama's models say `False` (`local_http.py:455`). If the model-id overlay match fails (`planning.py:47-55`), the plan says `tool_execution_mode="native"` and `willAttemptToolLoop: true`, then `ChatHarness.run_turn` silently falls through on `hasattr(provider, "chat_completion")` (`harness/__init__.py:145`) — which Ollama doesn't implement — and the turn runs with no tool loop at all. The documented trace-triage step 1 reports a plan the runtime never executed.
