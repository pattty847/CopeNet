@AGENTS.md

## Gemini-Specific Notes

`AGENTS.md` is the primary repository guide. This file adds Gemini-specific operating rules for future provider and search-oriented work.

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

### What Gemini Should Usually Avoid

Do not casually edit these high-conflict files unless explicitly assigned:
- `src/copenet/orchestrator.py`
- `src/copenet/host/static/app.js`
- `src/copenet/host/static/index.html`
- `src/copenet/host/ws_server.py`

Do not:
- redefine CopeNet’s core tool protocol on its own
- invent product behavior that has not been chosen
- couple provider-specific search behavior into shared architecture without approval
- refactor session or transcript persistence

### Good Gemini Tasks

- draft a Gemini CLI provider adapter plan
- research web search / grounding integration points
- build isolated provider experiments in a dedicated worktree
- compare output shapes across providers
- produce test prompts and debugging matrices for model behavior

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
