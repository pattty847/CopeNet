# CopeNet Target

This is the durable north star. [ROADMAP.md](plans/ROADMAP.md) contains unfinished
work; [ARCHITECTURE.md](ARCHITECTURE.md) describes the current implementation.

## Product Thesis

CopeNet is a local operator gateway for frontier and local models: durable sessions,
provider-agnostic tools, explicit operator authority, inspectable evidence, and
purpose-built workspaces beyond chat.

The system should feel as capable as a coding-agent harness while remaining understandable
to someone who does not live in a terminal.

## Runtime

- Durable, append-only conversation history with honest provider continuity.
- Native tool calling where providers support it and a compatible fallback elsewhere.
- A small explicit core tool surface with approved domain tools added deliberately.
- Per-run provider/model provenance and operator-controlled runtime/Access changes.
- Policy—not model prose—controls authority.
- Observable tool activity, approvals, errors, and finalization.

## Personal Continuity

- Personas, memory, user notes, briefings, and return cues remain operator-visible.
- Model-proposed durable changes use draft → review/edit → approve.
- Global and project scope are explicit.
- Nothing silently rewrites identity, memory, or previous conversation history.

## Multi-Model Work

- Fleet and Research Lab coordinate models through explicit product workflows.
- Independent analysis remains independent until the workflow intentionally reveals it.
- Provider fallback, review, debate, and synthesis are visible rather than hidden routing.
- Shared coordination primitives preserve each lane's evidence and runtime provenance.

## Domain Workspaces

- Market Monitor, Research Lab, Meme Lab, and future domain workspaces combine data,
  tools, prompts, layouts, and durable outputs.
- A future declarative workspace manifest should let a model draft a workspace while the
  runtime validates capabilities and the operator approves what is instantiated.
- Domain workflows should answer recurring operator questions, not merely display data.

## Principles

- The transcript is context; summaries and compaction must remain inspectable.
- Providers stay thin and the harness stays provider-agnostic.
- Stored history is append-only.
- UI state tells the truth about what is live, mocked, blocked, or unavailable.
- Every automation has provenance, a failure state, and an operator control boundary.
