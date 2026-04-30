# CopeNet Harness Patch Shortlist V1

## Summary
Implement the first Hermes-derived harness improvements that directly target CopeNet’s current Gemma failure mode: shallow repeated reconnaissance, over-crediting weak context, and weak mid-loop recovery.

This wave should stay narrowly focused on repo/code tasks and should **not** add Telegram, approvals, or orchestration yet. The goal is to make local models less “confidently lazy” before we expand the surface area.

Chosen defaults:
- Treat `context.prepare` as **directional support**, not grounding, for repo/code tasks
- Add anti-repeat warnings/blocks for repeated identical `files.list`, `files.read`, and `files.search`
- Strengthen tool descriptions and follow-up prompts before changing the overall harness architecture again
- Add one new recovery path for shallow/repetitive tool behavior
- Re-run the live probe matrix after each intervention batch, not all at once

## Key Changes

### 1. Strengthen repo-tool semantics
Update the built-in repo tool descriptions so the model sees clearer tool intent up front.

Changes:
- `files.list`
  - describe it as reconnaissance only
  - explicitly say it is **not sufficient evidence** for architecture/bug/patch-style answers
  - tell the model to follow with `files.read` or `files.search`
- `files.read`
  - describe it as the primary grounding tool for code/repo claims
  - emphasize that file-backed claims should come from this tool
- `files.search`
  - describe it as directional discovery, useful for finding symbols/files before reading
  - emphasize it should usually lead to `files.read`
- `context.prepare`
  - narrow the description so it reads as a compact session/repo overview only
  - explicitly say it does not replace direct file inspection for repo/code claims

Apply this in the builtin tool descriptors, not only in harness prompts.

### 2. Reclassify grounding in the evidence ledger
Change the ledger so repo/code tasks stop over-crediting shallow context.

Changes:
- `files.list` remains `reconnaissance`
- `files.search` remains `directional`
- `files.read` remains `grounding`
- `context.prepare` becomes `contextual` or `supporting`, not `grounding`
- probe/runtime grounding checks for repo/code tasks should only count:
  - `files.read` as grounding
  - `files.search` as directional support
- `context.prepare` may still help satisfy “exploration happened” style checks, but not “grounded repo answer” checks

This change must flow through:
- turn-state evidence classification
- final-gate evaluation
- probe classification helpers

### 3. Add anti-repeat tool behavior
Add Hermes-style pushback at the tool layer for repeated low-value actions.

Behavior:
- Track consecutive identical tool calls per turn/session for:
  - `files.list` by normalized path
  - `files.read` by normalized path
  - `files.search` by normalized `(pattern, path)`
- Thresholds:
  - 3rd identical consecutive call returns a warning in tool output
  - 4th identical consecutive call returns a blocked/error-style result telling the model to stop repeating and use existing information
- Reset the consecutive counter when:
  - a different tool is executed
  - the same tool is executed with materially different arguments
- For `files.list`, the warning/block message should explicitly recommend:
  - `files.read` for direct evidence
  - `files.search` for broader discovery

This should live with the tool handlers/runtime state, not only in prompt text.

### 4. Add shallow-reconnaissance recovery in the harness
Teach the harness to recover when the model is technically using tools but doing useless reconnaissance.

New behavior:
- detect a shallow pattern in repo/code contracts:
  - repeated `files.list`
  - no `files.read`
  - optional `context.prepare`
  - final candidate or natural-language answer attempt
- when detected:
  - reject finalization
  - set a specific reason code such as `reconnaissance_saturation`
  - inject a stronger follow-up prompt that says the model has not inspected direct file evidence yet
  - explicitly require exactly one next action, biased to:
    - `files.read` if likely file targets already exist
    - `files.search` otherwise
- if the model repeats the same shallow move again after rejection, escalate the warning text further rather than silently looping

This should complement `FinalGate`, not replace it.

### 5. Tighten contract logic for repo/code tasks
Keep the current generic contract shape, but make repo/code behavior stricter.

Changes:
- `repo_explain`
  - finalization requires at least one `files.read`
  - `context.prepare` alone can never satisfy the contract
- `patch_plan`
  - finalization requires:
    - at least one `files.read`, or
    - `files.search` followed by a cited file target and then `files.read`
  - `context.prepare` alone can never satisfy the contract
- `repo_explore`
  - `files.list` may start the flow
  - but finalization still requires direct evidence beyond listing
- preferred next actions should bias more strongly away from `files.list` once any listing already happened

### 6. Make probe grading harsher and more informative
Update the probe suite so “barely grounded” no longer looks too healthy.

Changes:
- add explicit classification support for:
  - `reconnaissance_saturation`
  - `repeated_identical_tool_use`
  - `context_only_grounding`
- adjust repo/code grounding checks so `context.prepare` no longer counts as sufficient grounding
- distinguish stronger vs weaker success outcomes where possible:
  - grounded success
  - recovered after rejection
  - minimal success
- keep the existing live probe set, but make the report tell us whether success came from:
  - real file grounding
  - final-gate recovery
  - shallow-but-accepted behavior

## Test Plan

### Unit tests
- tool descriptor/export tests reflect stronger descriptions and unchanged public shape
- turn-state evidence classification:
  - `files.read` = grounding
  - `files.search` = directional
  - `context.prepare` != grounding
- repeated identical tool call tracker:
  - warning on 3rd consecutive call
  - block/error on 4th
  - reset on different tool or changed args
- final-gate rejects repo/code finals when only:
  - `files.list`
  - `files.list + context.prepare`
  - repeated `files.search` with no read
- final-gate emits `reconnaissance_saturation` when applicable

### Integration tests
- repo explanation cannot finalize after listing-only flow
- repo explanation cannot finalize after `context.prepare` plus listing-only flow
- repeated identical `files.list` eventually yields a warning/block result
- repeated identical `files.read` and `files.search` also escalate correctly
- native LM Studio loop recovery path:
  - shallow final attempt
  - rejection
  - forced follow-up
  - subsequent grounded read succeeds
- prompted fallback loop still works for providers without native tool calls

### Live acceptance checks
Run:
- `/Users/copeharder/Programming/CopeNet/scripts/live_probe_matrix.py --providers lm-studio --lm-model google/gemma-4-e4b --expect-trace`

Success criteria:
- fewer `ungrounded_repo_answer`
- fewer listing-only tool chains
- visible `reconnaissance_saturation` or equivalent recovery where Gemma previously spammed `files.list`
- `patch_plan_probe` and `artifact_dependency_probe` show direct file grounding more often
- no regression in same-session repeat behavior

## Assumptions
- This wave stays within CopeNet’s current local repo/code harness scope
- No new public RPC surface is needed for this patch set
- No Telegram, approvals, `execute_code`, or delegation changes are included here
- Native LM Studio tool calling remains the preferred execution path for Gemma-class models
- If any success-grading rename would create unnecessary churn, keep `batch_success` but add clearer metadata/reason fields rather than renaming the whole classification taxonomy
