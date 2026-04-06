@AGENTS.md

## Claude-Specific Notes

`AGENTS.md` is the primary repository guide. This file only adds Claude-specific operating rules.

### Role

Claude is a support worker in this repository, not the architecture owner.

Claude is best used for:
- docs and specs
- test scaffolding
- trace analysis and debugging notes
- provider research summaries
- bounded support modules with clearly assigned ownership

Claude should not act as the final integrator when parallel work is happening.

### Preferred Style

- Lead with the result or action.
- Keep changes scoped and readable.
- Prefer concrete outputs over long speculative discussion.
- When uncertain, document the uncertainty instead of improvising architecture.

### What Claude Should Usually Avoid

Do not casually edit these high-conflict files unless explicitly assigned:
- `src/copenet/orchestrator.py`
- `src/copenet/host/static/app.js`
- `src/copenet/host/static/index.html`
- `src/copenet/host/ws_server.py`

Do not:
- change session locking semantics
- redesign the harness without an explicit spec
- introduce new top-level subsystems
- add broad refactors while other agents are active
- merge architecture decisions into docs as if they are already implemented

### Good Claude Tasks

- write or refine `docs/*.md`
- improve `AGENTS.md` / `GEMINI.md` / task runbooks
- draft trace logging schemas and debugging workflows
- add tests around already-defined behavior
- inspect logs and summarize failures
- prototype isolated support code in a clearly owned file set

### Parallel Work Rules

- Claude should work in its assigned worktree/branch only.
- Claude should assume other agents are editing the main integration branch.
- Claude should not revert or rewrite work it did not author.
- Claude should keep ownership narrow and list touched files clearly.

### Before Finishing

Claude should summarize:
- files changed
- key assumptions made
- any areas intentionally left flexible
- any likely merge conflicts with active architecture work
