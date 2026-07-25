# Model Context Architecture

## Goal

Give every model request the smallest intentional context for its purpose.
Prompt text, transcript replay, tool schemas, and tool results should each have
one owner and remain observable at the provider boundary.

## Current Baseline

The provider-boundary characterization tests pin today’s behavior for:

- OpenAI Responses instructions, message items, tool schemas, and tool follow-ups
- Claude CLI `-p` text, repeated prompted-tool instructions, tool results, and resume arguments

These tests are the safety net for the changes below.

## Request Purposes

| Purpose | Base behavior | Persona | Memory | Tools |
|---|---|---|---|---|
| General chat | Minimal helpful-assistant prompt | Explicit persona context, without agent operating notes | No automatic relevance-ranked digest | Only when enabled for the session |
| Code work | Selected code-oriented profile | Persona context plus `AGENTS.md` operating notes | No automatic relevance-ranked digest | Policy-filtered manifest |
| Utility | A task-specific instruction only | None | None | None unless the utility explicitly requires one |
| Specialized workflow | Workflow-owned prompt | Only when the workflow opts in | Workflow-owned evidence | Workflow-owned manifest |

Code-oriented profiles are currently `builder`, `code-review`, `debug`, and
`refactor`. This mapping is centralized policy, not provider behavior. A future
UI/API field can replace profile inference with an explicit request purpose
without changing the context rules.

## Composition Order

For an interactive model turn:

1. selected base profile
2. Access overlay
3. allowed persona context
4. harness-owned workspace/tool instructions
5. transcript or provider-resume state
6. current user message
7. tool calls and results produced during the turn

Tool descriptions stay in provider-native schemas when supported. Prompt-only
tool protocols remain a compatibility path, not the architecture.

## Memory Policy

Relevance-ranked memory is disabled for automatic prompt injection until its
selection, privacy, token budget, provenance, and operator controls are designed.
Memory records remain available through explicit tools and UI surfaces.

Persona-owned files remain governed by the persona privacy tier. `AGENTS.md` is
an operating guide for code work and is not general conversational pretext.

## Long-Chat Policy

Do not silently delete durable transcript entries. Provider input should instead
use an explicit context-window strategy:

1. preserve recent user/assistant turns
2. preserve unresolved tool-call/result pairs
3. compact stale tool output first
4. omit oldest complete turns from the provider view at the input budget
5. add a provenance-linked conversation summary when needed
6. retain full history in storage for audit and export

CopeNet currently uses a conservative 48K estimated-token transcript budget.
The estimate and omitted item count are traced. Provenance-linked summaries are
still future work; omission never mutates the stored transcript.

## Claude Transport

Claude CLI 2.1 exposes a native `--system-prompt` flag. CopeNet uses that
channel instead of embedding system text into `-p`, disables built-in tools,
and passes `--setting-sources=` so filesystem settings and `CLAUDE.md` do not
silently become model context.

Anthropic's Agent SDK is the intended transport replacement. Its isolation
defaults match this policy, it supports typed messages and context-usage
inspection, and it bundles a compatible CLI. Migrating transport should preserve
the provider-boundary tests and must not re-enable Claude's independent tool
harness alongside CopeNet's tool runtime.

## Delivery Order

1. Characterize provider boundaries. **Done.**
2. Centralize request-purpose context policy and simplify defaults. **Done.**
3. Route utility calls through purpose-specific requests. **Done.**
4. Replace Claude prompt embedding with its native system-prompt path. **Done.**
5. Add context-window budgeting. **Done; summaries remain future work.**
6. Add safe prompt diagnostics that expose source sizes and token estimates. **Done.**
7. Replace the raw Claude subprocess adapter with the Agent SDK transport.
