# Context Conveyor Next Steps

Status: accepted implementation plan
Date: 2026-07-25
Inputs:

- `docs/plans/MODEL_CONTEXT_ARCHITECTURE.md`
- `docs/plans/PROVIDER_TRANSPORT_EVALUATION.md`
- `docs/audit/claude-opus-5-context-conveyor-review-2026-07-25.md`

## Outcome

Every provider call should receive the context required for its exact purpose,
with:

- one owner for each instruction source;
- no accidental provider fallback identity;
- no duplicated transcript or tool protocol;
- only relevant tools;
- complete and consistent tool-result information;
- model-aware text, image, reasoning, and tool-output budgeting;
- durable transcript preservation;
- observable provider-bound input;
- Access remaining the sole authority boundary.

This work optimizes context without treating fewer tokens as the goal. Useful
requirements, evidence, and unresolved state stay available. Irrelevant,
duplicated, stale, or recoverable material is omitted or compacted.

## Decisions

### Stay on the Claude CLI

Keep `claude -p` as the production Claude transport. The Agent SDK remains
deferred and is not required by this plan.

CopeNet will continue to:

- use Claude subscription authentication;
- avoid `ANTHROPIC_API_KEY` when subscription usage is intended;
- supply CopeNet's prompt through `--system-prompt`;
- disable Claude Code built-in tools with `--tools ""`;
- isolate filesystem settings with `--setting-sources=`;
- use Claude-owned session resume;
- keep CopeNet as the tool and permission authority.

Do not use `--bare`; it disables the normal OAuth/keychain subscription path.

### Use a 100K provider-input target

Replace the fixed 48K text-only assumption with a model-aware budget:

```text
effective input budget =
    min(100K target, provider/model safe input capacity)
    minus reserved output/reasoning headroom
```

The exact reserve must come from model metadata where available and a
conservative provider fallback otherwise. Never assume every provider or local
model has a 200K window.

Do not raise the limit until the estimator can see images, reasoning,
instructions, tool schemas, and tool results. A larger inaccurate budget only
hides overflow for longer.

The full transcript remains durable. The budget controls only the view sent to
the provider.

### Purpose selects relevance; Access selects authority

Initial request purpose is host-owned and deterministic:

- the calling workflow determines known utility/specialized purposes;
- the selected profile determines general-chat versus code work;
- explicit future UI/API purpose may override only when product semantics call
  for it.

Do not spend a separate model call classifying every request. The model may
request additional tool disclosure during a turn, but it may never expand its
own Access or gain a tool outside server policy.

### Tool contracts are not assumed to be memorized

For native tool calling, a tool normally must be declared on the provider call
where it can be invoked. CopeNet currently resends tool schemas on every
OpenAI Responses call and every tool-loop step. Claude receives the prompted
manifest in its system prompt on each CLI invocation, subject to resume
semantics that still need a probe.

Stable schemas should remain stable for provider prompt caching, but caching is
not permission, memory, or context ownership.

Use two optimizations in order:

1. Send only the deterministic purpose bundle needed for the request.
2. If the catalog later becomes large enough, add model-requested deferred
   disclosure for additional authorized bundles.

Do not make important schemas cryptically short merely to save tokens. Remove
irrelevant tools first, then remove duplicated prose while retaining behavioral
and safety constraints.

## Target request purposes

| Purpose | Initial context | Initial tools |
|---|---|---|
| General chat | Minimal identity, optional persona, selected conversation | None or a small general bundle chosen by product policy |
| Code work | Code profile, Access overlay, persona, `AGENTS.md`, conversation | Repository/shell/plan bundle filtered by Access |
| Utility | One task instruction and exact input | None unless the utility explicitly requires one |
| Web research | Research instruction and evidence state | Web search/fetch only |
| Market | Market workflow instruction and evidence | `market.*`, plus explicitly selected evidence tools |
| Persona/memory | Exact persona or memory operation context | Relevant persona/memory tools only |
| Specialized workflow | Workflow-owned prompt and evidence | Workflow-owned allowlist |

Known utility calls such as title generation must not inherit transcript,
persona, Access prose, workspace instructions, or tool schemas. Title
generation needs only its title instruction and the selected source message(s).

## Target tool disclosure

### Phase-one bundles

Keep bundle definitions explicit and searchable. Suggested starting point:

- `code-read`: `files.read`, `files.rg`, safe shell inspection
- `code-write`: `files.write`, `files.edit`, unrestricted shell only when Access
  grants it
- `planning`: `plan.write`
- `web`: `web.search`, `web.fetch`
- `market`: `market.*`
- `persona-memory`: persona, memory, and user-note tools

Exact tool IDs remain canonical. Bundles select relevance; existing tool
category policy still grants or denies authority.

### Deferred disclosure, later

If purpose bundles remain expensive, add one small discovery contract capable
of returning:

- available authorized bundle names;
- one-line bundle descriptions;
- tool IDs in a selected bundle;
- schemas for a selected bundle.

The turn then receives an updated active manifest on the next provider call.
The harness must track the active tool IDs and reject calls to anything not
active, even when the guessed tool would otherwise fall into an allowed Access
category.

Deferred disclosure is not part of the first implementation pass. With the
current 17-tool catalog, purpose filtering is simpler, faster, and easier to
verify.

## Implementation phases

### Phase 1 — Establish one prompt owner

Status: **implemented** (2026-07-25).

Changes:

1. Compose profile and Access text inside the orchestrator for every
   `ChatSendRequest`.
2. Treat an explicitly supplied `system_prompt` as a deliberate override.
3. Stop composing only in `rpc_chat.py`.
4. Remove or explicitly trace provider-created fallback identities.
5. Thread the resolved request purpose into provider-boundary tracing.

Acceptance:

- WebSocket, REST, SSE, CLI chat, Fleet, and coordination lanes receive the
  same profile/Access prompt for the same binding.
- Claude never unintentionally falls back to its default Claude Code identity.
- OpenAI never silently substitutes `OPENAI_CODEX_DEFAULT_INSTRUCTIONS`.
- Utility calls remain isolated.

Tests:

- Parametrize all `ChatSendRequest` entry points.
- Assert non-empty expected instructions for interactive calls.
- Assert no ambient prompt for title generation and other utilities.

### Phase 2 — Make prompted tools unambiguous and policy-bound

Status: **implemented** (2026-07-25).

Changes:

1. Require an explicit CopeNet tool-call delimiter.
2. Parse JSON only inside that delimiter.
3. Accept only the canonical `tool_id` plus `arguments` shape.
4. Remove bare-command and generic `name` fallbacks.
5. Reject any tool ID not in the exact active manifest.
6. Distinguish malformed attempted calls from ordinary prose.
7. Return one corrective follow-up for malformed tool syntax rather than
   silently completing the turn.

Acceptance:

- JSON examples, quoted files, and explanatory prose cannot execute tools.
- Guessed off-manifest tools cannot execute.
- Malformed tool requests are visible in traces and correctable.
- Access remains enforced by the registry after manifest validation.

Tests:

- Prose containing `{"command":"whoami"}` executes nothing.
- Prose describing a file-write call executes nothing.
- A correctly delimited active tool executes once.
- A correctly delimited inactive tool is rejected.
- Malformed delimited JSON produces a parse event and corrective follow-up.

### Phase 3 — Unify the tool-result contract

Status: **implemented** (2026-07-25).

Changes:

1. Send the same model-facing envelope on prompted, native Chat, and Responses
   paths:

   ```json
   {
     "ok": false,
     "summary": "blocked",
     "body": {},
     "error": "approval required"
   }
   ```

2. Mark tool results as untrusted observations, never operator instructions.
3. Keep handler output bodies intact while making failures actionable.
4. Use one canonical success key; remove `ok`/`success` drift where compatible.

Acceptance:

- Policy blocks, handler errors, and successful empty results are
  distinguishable.
- Models do not retry merely because the failure reason was discarded.
- All three tool loops pass the same contract test.

### Phase 4 — Fix budget measurement, then raise the target

Status: **implemented** (2026-07-25).

Changes:

1. Count system/developer instructions.
2. Count tool descriptions and schemas.
3. Count text messages, tool calls, and tool outputs.
4. Account for image count, dimensions/detail where available, and encoded
   payload size as a conservative fallback.
5. Count encrypted reasoning, compaction, and unknown structured items using a
   safe serialized-size fallback.
6. Reserve output/reasoning headroom.
7. Re-apply the budget during every tool-loop step, after stale-output
   compaction.
8. Set the normal target to 100K after these measurements are enforced.

Acceptance:

- A multi-image conversation cannot report a near-zero estimate.
- Unknown item types cannot consume zero estimated context.
- Tool loops cannot grow beyond the effective per-model limit.
- Recent complete turns and unresolved tool pairs remain intact.
- Durable transcript storage remains untouched.

Tests:

- Text-only, image, reasoning, unknown-item, and long-tool-loop fixtures.
- Model metadata below 100K lowers the effective budget.
- Large-context models use the 100K target with explicit headroom.

### Phase 5 — Resolve Claude resume behavior

Investigation first; do not guess.

Run targeted subscription-backed probes:

1. A sentinel `CLAUDE.md` with `--setting-sources=` and a CopeNet
   `--system-prompt` to verify filesystem isolation.
2. A resumed session whose second turn changes the system/Access prompt to
   determine whether `--system-prompt` changes take effect on `--resume`.
3. A two-step tool call to inspect exactly what Claude sees in the follow-up.

Then:

1. On resumed tool steps, send only new tool results and the minimal continuation
   instruction.
2. Do not repeat the full transcript or previous assistant tool-request prose.
3. If resumed Claude sessions pin their original system prompt, version the
   provider session when Access/profile context changes rather than pretending
   the new prompt took effect.
4. Keep the raw CLI adapter.

Acceptance:

- No duplicated transcript inside a resumed Claude conversation.
- The tool protocol remains present and effective after resume.
- Mid-session Access changes have explicit, truthful semantics.
- No probe uses API-key billing.

### Phase 6 — Purpose-filter tool manifests

Changes:

1. Introduce explicit purpose-to-tool-bundle selection.
2. Intersect relevant tool IDs with the existing Access policy.
3. Make specialized workflows provide exact tool allowlists.
4. Keep utility manifests empty by default.
5. Make the Responses coding-agent directive purpose-aware.
6. Add a stable serialized-manifest token ceiling test.

Acceptance:

- General chat does not advertise `market.*` or persona-authoring tools without
  a relevant purpose.
- Code work does not advertise market tools.
- Title generation receives no tools.
- Market work retains every required market capability.
- Full Access adds authority only inside the relevant bundle.
- Stable schema ordering preserves prompt-cache-friendly prefixes.

### Phase 7 — Preserve structured provider semantics

Changes:

1. Keep OpenAI Responses input structured even when tools are disabled.
2. Preserve images regardless of `allow_tools`.
3. Surface incomplete Responses streams as incomplete, never completed.
4. Reject malformed native tool arguments rather than executing with `{}`.
5. Trace unknown output item types.
6. Before adding public Responses, build the raw output-item persistence/replay
   lane required for reasoning and compaction continuity.

Acceptance:

- Tool availability changes only the tool array, not conversation structure.
- Vision input survives with tools on or off.
- Unknown/new provider output shapes are observable.

### Phase 8 — Add actual usage and a model-input ledger

Changes:

1. Capture provider-reported input, cached-input, output, and reasoning usage.
2. Accumulate usage across every tool-loop call.
3. Add one per-provider-call ledger containing:
   - purpose;
   - instruction-source sizes and stable hashes;
   - replayed, omitted, and compacted item counts;
   - active tool IDs and serialized schema estimate;
   - image counts/details;
   - provider resume/replay mode;
   - estimated tokens;
   - actual provider usage when returned.
4. Never log credentials, sensitive full prompts, or hidden reasoning.

Acceptance:

- An operator can explain what consumed context on every call.
- Estimates can be compared with actual usage and improved empirically.
- Prompt caching can be verified through cached-token usage where reported.

### Phase 9 — Reassess deferred tool disclosure and summaries

After real measurements exist, decide:

- whether purpose bundles have reduced the tool manifest enough;
- whether deferred schema disclosure saves more than its extra round trip costs;
- whether any conversation class regularly approaches the 100K target;
- whether provenance-linked summaries are necessary.

Do not add automatic conversation summaries simply because the context window is
large. Add them only when measured long-session behavior shows omission and
tool-result compaction are insufficient.

## Context retention policy

Preserve:

- user requirements and corrections;
- unresolved decisions;
- recent user/assistant turns;
- active plans;
- unresolved tool calls/results;
- exact evidence still needed for the answer.

Compact first:

- stale web fetch bodies;
- old shell output;
- superseded file reads;
- repeated diagnostics;
- completed intermediate tool observations that can be re-fetched.

Omit only from the provider view:

- oldest complete resolved turns after the effective budget is reached;
- irrelevant tool schemas;
- superseded recoverable detail already represented by a provenance-linked
  compact form.

Never delete or rewrite durable transcript entries as a context optimization.

## Verification commands

Run after each applicable phase:

```bash
uv run --extra dev pytest -q
python3 -m py_compile $(rg --files src/copenet -g '*.py')
```

For provider-visible changes, also run:

```bash
uv run --extra dev pytest -q tests/integration/test_claude_cli_prompt_contract.py
uv run --extra dev pytest -q tests/integration/test_responses_tool_loop.py
uv run --extra dev pytest -q tests/integration/test_tool_prompt_matrix.py
```

Use live probes only for the three Claude questions in Phase 5 and narrowly
scoped post-fix confirmation. Record the run IDs and inspect traces before
drawing conclusions from model self-report.

## Recommended execution boundary

Implement Phases 1–4 as the first coherent unit. They fix the incorrect prompt
ownership, unsafe prompted-tool parsing, lossy tool results, and false context
budget—the four issues most likely to create confusing or unsafe model behavior.

**Phases 1–4 are implemented as of 2026-07-25** (653 tests passing). Phase 5 is
the next unit and is investigation-first.

Stop and review traces/tests before Phase 5. Claude resume behavior must be
measured before changing its continuation protocol. Then implement Phases 6–8
as separate, reversible units.
