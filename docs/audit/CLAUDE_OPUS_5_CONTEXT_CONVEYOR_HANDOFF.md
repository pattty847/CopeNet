# Claude Opus 5 Review Handoff: CopeNet Model Context Conveyor

Use the text below as the complete task prompt for Claude Opus 5 while its
working directory is the CopeNet repository root.

---

You are performing an independent, evidence-driven architecture and code review
of CopeNet's model context conveyor.

CopeNet is an agent harness supporting multiple provider shapes, including
OpenAI Responses-style native tool calls and Claude Code CLI prompted tool use.
The most important product responsibility is to guide each model clearly inside
the world CopeNet gives it: the correct instructions, relevant context, durable
conversation state, tool definitions, tool results, permissions, and current
task—without accidental duplication, stale instructions, hidden local context,
or wasteful prompt growth.

The goal is not to make prompts as short as possible. The goal is to preserve
all useful context while removing accidental or irrelevant context, assign one
owner to every model-visible input, and make the final provider-bound request
observable and testable. We want the architectural quality demonstrated by
Codex and Claude Code: models should understand their environment because the
harness has intentionally and efficiently constructed that environment.

## Your assignment

Review exactly what changed in these four commits and evaluate the resulting
system at current `HEAD`:

- `1b36d71` — `test(harness): characterize provider model inputs`
- `fbdff1f` — `refactor(prompts): centralize context purpose policy`
- `cb08fdb` — `refactor(harness): unify model context conveyor`
- `3a54e56` — `docs(providers): evaluate subscription transport options`

Do not rely on the commit messages or design documents alone. Read the diffs,
follow the active runtime paths, inspect the tests, and compare the documented
intent with actual provider-bound behavior.

Start with:

- `AGENTS.md`
- `docs/plans/MODEL_CONTEXT_ARCHITECTURE.md`
- `docs/plans/PROVIDER_TRANSPORT_EVALUATION.md`
- `docs/plans/HARNESS_REBUILD_V2.md`
- `docs/TRACING.md`
- `src/copenet/core/model_request.py`
- `src/copenet/prompts/policy.py`
- `src/copenet/core/orchestrator/runtime.py`
- `src/copenet/core/orchestrator/messages.py`
- `src/copenet/core/harness/`
- `src/copenet/providers/claude_cli.py`
- `src/copenet/providers/openai_codex.py`
- the tests changed by the four commits

Then search outward to every caller that creates model-visible instructions,
messages, tool descriptions, tool results, summaries, memory/persona material,
specialized-workflow evidence, or utility prompts.

## Questions you must answer

### 1. Complete model-input inventory

Build a concise inventory of every circumstance in which CopeNet supplies text
or structured context to a model outside the current user's message:

- system/developer/base instructions;
- Access overlays and persona material;
- `AGENTS.md`, workspace instructions, memory, and user notes;
- transcript replay or provider-owned resume state;
- tool manifests and JSON schemas;
- prompted tool-use protocols;
- native tool calls and tool results;
- utility calls such as title generation, prompt optimization, merge, Pulse,
  browser decisions, market interpretation, and other specialized workflows;
- long-chat omission, compaction, or future summaries;
- retry/error/correction prompts;
- provider or harness metadata that becomes model-visible.

For each source, identify:

- its owner;
- its role or precedence;
- when it is included;
- its approximate size or budget;
- whether it can duplicate another source;
- whether it is traced or otherwise observable;
- how untrusted content is delimited from instructions.

Call out any model-visible injection path that bypasses the new
`ModelRequest`/purpose policy or cannot be explained from traces.

### 2. Context quality and efficiency

Determine whether the new architecture actually achieves "smallest intentional
context for the purpose" without deleting context the model needs.

Specifically verify:

- general chat receives a genuinely minimal default identity;
- code work receives `AGENTS.md` only when appropriate;
- utility requests do not inherit persona, transcript, workspace, or tools
  accidentally;
- specialized workflows own their evidence and tool surface explicitly;
- automatic memory injection is truly disabled everywhere intended;
- persona context is bounded, privacy-aware, and non-duplicative;
- the 48K estimated-token transcript budget is enforced on the real provider
  path, not merely recorded in configuration;
- complete tool-call/result pairs cannot be split by trimming;
- stale tool output is treated differently from valuable user/assistant
  conversation;
- omission is distinguishable from summary and never mutates the durable
  transcript;
- prompt-cache-friendly stable prefixes are preserved where practical.

Do not recommend reducing context merely to reduce tokens. Explain the expected
quality effect of every proposed removal, relocation, or compaction.

### 3. Provider correctness and parity

Trace representative first-turn, resumed-turn, tool-call, tool-result, long-chat,
and utility requests all the way to each provider boundary.

For Claude, verify:

- system text is passed through the native system channel rather than embedded
  into the user prompt;
- `--setting-sources=` and disabled built-in tools prevent unintended Claude
  Code context or a second tool harness;
- resumed sessions do not create duplicated history, duplicated prompted-tool
  instructions, or stale system instructions;
- the prompted-tool protocol and its tool-result envelope are robust against
  delimiter confusion, malformed JSON, and prompt injection;
- the proposed Agent SDK configuration in the transport evaluation is actually
  sufficient to suppress filesystem settings, MCP, skills, plugins, native
  tools, and inherited API-key billing;
- raw-CLI-created session IDs can be migrated safely to the SDK, or receive an
  explicit versioned fallback;
- SDK exception failures and error-bearing result messages would both map to
  CopeNet failures.

For OpenAI Responses, verify:

- instructions, input items, tool schemas, tool calls, and tool outputs have one
  clear owner;
- `store:false` replay preserves every item required for reasoning continuity;
- encrypted reasoning, compaction, phase, and unknown future output items are
  either preserved or deliberately unsupported with an explicit consequence;
- prompt caching and token accounting remain correct across tool-loop steps;
- the current custom OAuth/backend integration is characterized honestly;
- an official public Responses adapter would be more than a URL/authentication
  substitution;
- Codex app-server is correctly treated as a complete agent runtime rather than
  a transparent raw provider, including automatically loaded instruction
  sources and built-in tools.

Separate true cross-provider invariants from areas where provider-specific
semantics should remain explicit.

### 4. Tool-context design

Assess both the quality and cost of the tool surface:

- Is every always-advertised tool relevant to the current purpose?
- Should tool availability be narrowed by request purpose or workflow in
  addition to Access policy?
- Are descriptions concise enough for repeated model consumption while still
  explaining exact behavior, authority, evidence, side effects, and argument
  constraints?
- Are prompted tools and native tools semantically equivalent where intended?
- Is there one canonical model-facing tool-result envelope?
- Can large tool results overwhelm the context or contain instruction-like text
  that is insufficiently marked as untrusted evidence?
- Are errors actionable without causing wasteful correction loops?

Estimate the fixed token cost of the normal tool manifest and identify the
largest contributors. Recommend description changes only when you can explain
what behavioral signal is preserved or improved.

### 5. Observability and evaluation

Determine whether an operator can reconstruct exactly what the model saw for
each provider call without logging secrets or hidden reasoning.

Evaluate whether traces should expose a per-call model-input ledger containing:

- request purpose;
- instruction sources and estimated tokens;
- replayed/omitted/summarized transcript counts;
- tool-schema IDs and estimated tokens;
- tool-result sizes and truncation/compaction decisions;
- provider resume identifiers or response-chain mode;
- total estimated input size;
- stable hashes rather than sensitive full text where appropriate.

Propose deterministic tests and a very small live-probe matrix that would catch
semantic regressions. Do not run live provider prompts or spend subscription/API
quota during this review.

### 6. Compare against mature agent-harness practices

Use current public Anthropic Claude Code/Agent SDK and OpenAI Codex/Responses
documentation where it materially informs the review. Prefer primary sources
and cite them directly.

Do not pretend to know proprietary hidden prompts or undocumented internal
implementation details. Compare architectural properties instead:

- instruction hierarchy and ownership;
- context isolation;
- session continuity;
- compaction and raw-item preservation;
- tool discovery and narrowing;
- untrusted tool-output handling;
- permission authority;
- cancellation and recovery;
- prompt caching;
- context/token telemetry;
- reproducible provider-boundary tests.

If CopeNet should intentionally differ from Codex or Claude Code, say why.

## Required output

Create exactly one new file:

`docs/audit/claude-opus-5-context-conveyor-review-2026-07-25.md`

Do not edit production code, tests, existing documentation, configuration, or
the handoff file. Do not commit anything. Leave unrelated working-tree files
untouched, including `tmp_sec_parse_apple.py` if it is present.

The review file must contain:

1. **Executive verdict** — what improved, what remains structurally weak, and
   whether the current direction is correct.
2. **Verified model-input map** — a compact table or flow showing actual current
   composition and provider delivery.
3. **Findings** — ordered by `P0` through `P3`, each with:
   - concrete evidence and file/symbol references;
   - the exact model-visible consequence;
   - why existing tests do or do not catch it;
   - a focused recommended correction;
   - confidence level.
4. **What the prior work got right** — retain these invariants explicitly so a
   cleanup does not regress them.
5. **Claude SDK verdict** — proceed, defer, or reject, with exact migration
   gates.
6. **OpenAI transport verdict** — current custom transport, public Responses,
   and Codex app-server as three distinct choices.
7. **Target context architecture** — the smallest practical end state, avoiding
   speculative abstraction.
8. **Implementation order** — small, reversible phases with validation after
   each phase.
9. **Test/probe plan** — deterministic tests first, narrowly scoped live probes
   second.
10. **Open decisions** — only decisions that genuinely require product-owner
    judgment.
11. **Sources consulted** — code paths, commits, traces/tests, and primary vendor
    documentation.

Prioritize correctness and specificity over volume. A surprising conclusion is
welcome if the evidence supports it. Do not rubber-stamp the existing design,
and do not propose a rewrite merely because a cleaner abstraction is
imaginable.

Before finishing, run:

```bash
git diff --check
git status --short
```

Confirm that the only file you created is the requested review file and report
that path in your final response.

---
