# TARGET — what CopeNet is building toward

This is the standing "north star" doc. It describes the destination, not the
current state (that's `AGENTS.md` / `docs/architecture.md`). Every PR description
should reference which TARGET section it serves.

Created during the harness rebuild (see `docs/plans/HARNESS_REBUILD_V2.md`).

---

## The one-line target

CopeNet is a **personal continuity engine** built around frontier-model
orchestration over OAuth — a harness that works as well as Claude Code / Codex
CLI / OpenClaw, with personal layers (persona, memory, briefing, return cues)
built on top once redesigned around explicit operator opt-in.

---

## Layer 1 — Harness (the foundation)

**Target: Claude Code / Codex CLI / OpenClaw parity.**

- Real multi-turn conversation history sent every turn (✅ Phase 1).
- Native function calling via the provider's tool interface, not text parsing
  (✅ Phase 2 for openai-codex Responses API).
- A small, sharp tool surface — five primitives the model composes
  (✅ Phase 3: files.read/write/edit/rg + shell.exec).
- A chat experience that narrates: inline thinking between tool calls, grouped
  tool chips, diff previews, robust reconnect (◑ Phase 4 — thinking + reconnect
  landed; chip grouping / diff preview are follow-ups).
- Prompt caching, reasoning effort, and parallel tool calls used where the
  endpoint supports them (✅ wired on the Responses path).

**Not yet / deferred:** token-budget compaction, progressive tool-schema
disclosure, local-model (LM Studio/Ollama) Responses parity, multi-agent
orchestration (see Layer 3).

## Layer 2 — Personal layers (dormant, preserved)

Persona, identity, memory, and profile auto-update are **gated off** during the
rebuild (`COPNET_AUTO_MEMORY_EXTRACTION` / `COPNET_AUTO_PROFILE_EXTRACTION`,
default false). They come back through a clean redesign with explicit operator
opt-in — never silent keyword auto-mutation of session state.

Briefing, return cues, Pulse, and Merge are live but degraded; each gets its
own focused pass when it's worth attention.

## Layer 3 — Multi-agent orchestration (the next frontier)

Multiple frontier models (Codex / Claude / Gemini) working together on one
project, coordinated by a "head honcho" router that selects or chains providers
by turn semantics. CopeNet's provider registry + the Phase 1/2 shared
transcript + native tool loop are the substrate. See
`docs/plans/MULTI_AGENT_ORCHESTRATOR.md`.

---

## Principles

- The transcript is the context. No synthetic state blobs.
- The model decides routing and when it's done. The runtime enforces authority
  (policy), not intent.
- Each change is independently shippable, reviewable, revertable.
- Working paths are kept until their replacement is proven; dead code is swept,
  not left half-removed.
