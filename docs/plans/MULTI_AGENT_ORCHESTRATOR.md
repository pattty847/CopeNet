# Multi-Agent Orchestrator

**Status:** foundation landed (selection + fallback + adapter, unit-tested);
NOT yet wired into the live `send_chat` runtime — awaiting product direction.

**Grounded in:** the harness rebuild (`HARNESS_REBUILD_V2.md`). The Phase 1
shared transcript (`build_chat_messages` / `responses_items`) and the Phase 2
native tool loop are the substrate this layer coordinates over.

---

## Goal

Route a turn between provider **roles** and run a provider **chain with
fallback**, so multiple frontier models cooperate on one project under a single
"head honcho" router:

- **heavy lifting** → Codex (`openai-codex`) — best native tool calling
- **thinking** → Claude (`claude-cli`) — accuracy / review
- **breadth** → Gemini (`gemini`, not in the registry yet) — alternatives

## Where it sits

```
send_chat (runtime)            ← owns session state, transcript, run records
   │
   ▼
MultiAgentOrchestrator         ← NEW: selects WHICH provider runs, with fallback
   │   select_provider_chain(route) → ordered [primary, ...fallbacks]
   │   execute_with_fallback(chain, run_one)
   ▼
ChatHarness.run_turn           ← owns HOW one turn runs against ONE provider
   ▼
provider.run / stream_responses
```

The orchestrator is deliberately decoupled from the runtime via an injected
`run_on_provider(provider, provider_id)` callable, so it is unit-testable and
can be wired in incrementally.

## Modules (`src/copenet/core/multiagent/`)

- **`provider_selector.py`** — pure decision logic. `select_provider_chain(route,
  available_provider_ids, role_map)` → `ProviderSelection(primary, chain,
  rationale, unavailable)`. Route→role preferences:
  - `direct_response` → breadth, thinking, heavy_lifting (fastest first)
  - `ask_clarifying_question` → thinking, breadth
  - `call_tool` → heavy_lifting, thinking (Codex first for native tools)
  - `multi_step_agent_loop` → heavy_lifting, thinking, breadth (chain)
  - `create_or_update_artifact` → heavy_lifting, thinking
  - `refuse_or_redirect` → thinking
  - unknown → heavy_lifting, thinking, breadth
  Unavailable providers (e.g. Gemini today) are filtered out gracefully.

- **`fallback_executor.py`** — `execute_with_fallback(chain, run_one,
  should_retry, abort_event, timeout_s, trace)`. Tries each provider; falls
  through on exception, timeout (`asyncio.wait_for`), or a successful-but-
  rejected result (`should_retry` → the "Claude uncertain → ask Gemini" case).
  Returns `FallbackOutcome(ok, provider_id, value, attempts)`.

- **`orchestrator_adapter.py`** — `MultiAgentOrchestrator(providers, role_map,
  trace)`. `plan_selection(route)` resolves the chain; `run_turn(route,
  run_on_provider, ...)` selects + runs with fallback, returning
  `MultiAgentTurnResult(selection, outcome)`.

## Trace vocabulary

`multiagent_selection`, `multiagent_attempt`, `multiagent_fallback`,
`multiagent_completed`, `multiagent_exhausted`, `multiagent_aborted`,
`multiagent_fallback_empty`. All carry provider id + attempt index for the
inspector.

## Success criteria (met by `tests/unit/test_multiagent_orchestrator.py`)

- ✅ One turn flows through provider selection without blocking.
- ✅ Fallback chain works (Codex fails → Claude succeeds; also timeout +
  uncertain-result fallthrough).
- ✅ Trace events emitted and loggable.
- ✅ Selection is route-driven and availability-aware (missing Gemini handled).

## Wiring it into `send_chat` (the next step, pending direction)

The HarnessDecision `route` is already parsed per turn (trace-only today). To go
live:
1. In `runtime.send_chat`, after `plan_turn` + `resolve_harness_decision_record`,
   build a `MultiAgentOrchestrator(providers=orchestrator._providers,
   trace=trace.record)`.
2. `run_on_provider` = a closure that calls `harness.run_turn(provider=...,
   messages=chat_messages, ...)` for the chosen provider and drains its event
   stream into the existing emit/transcript/run-record path (which already
   updates session state — success criterion 4).
3. Decide the policy: only multi-route (`multi_step_agent_loop`) chains across
   providers, or every route? Per-turn vs. per-session provider affinity?
4. Cross-provider context: replay uses `responses_items` so a switch mid-task
   re-sends the full transcript to the new provider — already supported.

### Open questions for the operator
- Is routing per-turn, or does a session pin a provider once chosen?
- For `multi_step_agent_loop`, is the chain sequential review (Codex drafts →
  Claude reviews → Gemini alternatives as separate turns) or fallback-only?
- Add a real Gemini provider, or keep `breadth` mapped to an available model?
- Should fallback be silent, or surfaced in the chat as "Codex failed, Claude
  took over"?
