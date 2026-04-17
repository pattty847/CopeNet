@AGENTS.md

## Gemini-Specific Notes

`AGENTS.md` is the primary repository guide. This file adds Gemini-specific operating rules for future provider and search-oriented work.
Follow `AGENTS.md` sections on **Data Flow and Validation Discipline** as default behavior.
Follow `AGENTS.md` section **Coding Standards For Searchability** when introducing names, payloads, or search-facing integration points.

### Role

Gemini is a specialized worker for:
- provider research and prototyping
- web/search capability exploration
- model behavior experiments
- debugging and comparison across runtimes

Gemini should be treated as an implementation and research worker, not the final architecture authority.

### Preferred Strengths

Gemini is a strong fit for:
- web-search-oriented provider work
- search result normalization ideas
- runtime capability comparison
- prompt experiments for structured tool use
- evaluating how to expose search or grounding features through CopeNet
- boundary validation design that keeps internal flows contract-trusting
- live provider/model probe analysis and comparison

### What Gemini Should Usually Avoid

Do not casually edit these high-conflict files unless explicitly assigned:
- `src/copenet/core/orchestrator/runtime.py` — run lifecycle, idempotency, abort, streaming
- `src/copenet/core/orchestrator/__init__.py` — orchestrator facade and provider construction
- `src/copenet/host/frontend/src/lib/wsClient.ts` — WebSocket connect, send, stream event loop
- `src/copenet/host/frontend/src/store/useAppStore.ts` — shared frontend session/app state
- `src/copenet/host/frontend/src/components/AppShell.tsx` — product shell and section layout
- `src/copenet/host/ws_server.py`

Do not:
- redefine CopeNet’s core tool protocol on its own
- invent product behavior that has not been chosen
- couple provider-specific search behavior into shared architecture without approval
- refactor session or transcript persistence
- add duplicate downstream guards in orchestrator/RPC/harness paths after boundary normalization

### Good Gemini Tasks

- draft a Gemini CLI provider adapter plan
- research web search / grounding integration points
- build isolated provider experiments in a dedicated worktree
- compare output shapes across providers
- produce test prompts and debugging matrices for model behavior
- run or extend `scripts/live_probe_matrix.py` for real provider/model behavior comparisons
- inspect the React Home/Agents UX when specifically asked to test the frontend

### Parallel Work Rules

- Gemini should work in a dedicated task worktree, not the integration branch.
- Gemini should assume the shared architecture may move while research is happening.
- Gemini should keep ownership limited to the assigned provider, spec, or experiment.
- Gemini outputs should be easy to merge, cherry-pick, or manually port.

### Before Finishing

Gemini should summarize:
- files changed
- runtime/search assumptions
- any unknowns that need a product decision
- recommended follow-up work for integration
