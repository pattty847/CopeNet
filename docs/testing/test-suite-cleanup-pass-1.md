# Test Suite Cleanup Pass 1

## Summary

This pass made a bounded cleanup of the audited suite. It strengthened two
truthfulness gaps, removed only verified same-boundary duplicates or
tautological checks, consolidated one small transition table, removed four
confirmed-dead frontend helpers with their tests, and isolated deterministic
test infrastructure.

| Measure | Before | After | Delta |
|---|---:|---:|---:|
| Python test cases | 707 | 703 | -4 |
| Frontend test cases | 97 | 90 | -7 |
| Total test cases | 804 | 793 | -11 |
| Approximate logical groups | 782 | 767 | -15 |
| Python suite runtime | 27.44s | 27.29s | -0.15s |
| Frontend suite runtime | 1.23s | 1.09s | -0.14s |

Runtimes are framework-reported wall times and remain host-dependent. The
combined observed runtime moved from about 28.67s to 28.38s.

Sixteen test files changed: twelve Python test files and four frontend test
files. Five production files changed: the four tool-loop implementations/shared
helper and `src/copenet/host/frontend/src/lib/agentMobile.ts`. The production
tool-loop change fixes a cap enforcement defect; the frontend production change
removes four exports proven to have no callers.

Production files:

- `src/copenet/core/harness/tool_loop_common.py`
- `src/copenet/core/harness/tool_loop_prompted.py`
- `src/copenet/core/harness/tool_loop_native.py`
- `src/copenet/core/harness/tool_loop_responses.py`
- `src/copenet/host/frontend/src/lib/agentMobile.ts`

Test files:

- `tests/integration/test_tool_loop_cap_contract.py`
- `tests/integration/test_phase_0_quickwins.py`
- `tests/integration/test_phase_minus_1_baseline.py`
- `tests/integration/test_app_api_agents.py`
- `tests/integration/test_ws_rpc.py`
- `tests/integration/test_approval_gate.py`
- `tests/integration/test_multiturn_responses_e2e.py`
- `tests/unit/test_build_chat_messages.py`
- `tests/unit/test_market_backtester.py`
- `tests/unit/test_session_store.py`
- `tests/unit/test_tool_contracts.py`
- `tests/unit/test_workspace_intel_tools.py`
- `src/copenet/host/frontend/tests/agentMobile.test.ts`
- `src/copenet/host/frontend/tests/personaHomeStore.test.ts` (deleted)
- `src/copenet/host/frontend/tests/workspaceIntelStore.test.ts` (deleted)
- `src/copenet/host/frontend/tests/wsClientNormalization.test.ts`

Confidence was not reduced because every deletion was either covered at the
same boundary by an equal or stronger retained test, asserted only a direct
setter round-trip, or tested dead production code removed in the same change.
The old cap checks were replaced by three stronger behavioral cases.

## Changes completed

### Strengthened and replaced

- Deleted
  `tests/integration/test_phase_0_quickwins.py::test_max_tool_steps_was_lifted`
  and
  `tests/integration/test_phase_minus_1_baseline.py::test_tool_loop_caps_at_max_tool_steps`.
  Retained replacement:
  `tests/integration/test_tool_loop_cap_contract.py::test_tool_loops_execute_only_max_tool_steps_and_explain_the_cap`,
  parameterized for prompted, native Chat Completions, and OpenAI Responses
  loops. The old checks proved only a constant value or five below-cap prompted
  calls. The replacement protects the actual execution boundary.

- Strengthened
  `tests/integration/test_phase_minus_1_baseline.py::test_dispatch_rpc_returns_invalid_request_on_bad_param`.
  It now requires `INVALID_REQUEST`, the original request ID, an actionable
  message containing the rejected value, and a successful valid
  `chat.history` request through the same callback afterward.

### Verified duplicate deletions

- Deleted
  `tests/unit/test_workspace_intel_tools.py::test_tool_registry_does_not_expose_removed_experimental_tools`.
  Retained
  `tests/unit/test_tool_contracts.py::test_tool_registry_does_not_expose_removed_experimental_tools`,
  which checks the same `ToolRegistry` boundary and also proves a current
  manifest tool remains present.

- Deleted
  `tests/integration/test_phase_minus_1_baseline.py::test_idempotency_cache_still_dedupes_within_same_session`.
  Retained `tests/integration/test_orchestrator.py`'s same-session repeated
  `idempotency_key` case, which makes the same two sends through the
  orchestrator and requires the second result to be `cached`. The distinct
  cross-session isolation regression remains.

- Deleted
  `tests/unit/test_build_chat_messages.py::test_estimate_input_tokens_is_roughly_char_quarter`.
  Retained
  `tests/unit/test_context_budget.py::test_text_estimate_is_still_roughly_char_quarter`,
  which passes the same 400-character text shape to the same estimator and
  expects 100 tokens.

- Deleted
  `tests/unit/test_build_chat_messages.py::test_token_budget_always_keeps_oversized_current_turn`.
  Retained
  `tests/unit/test_context_budget.py::test_oversized_current_turn_is_always_kept`,
  which exercises the same trimming function and invariant with a more
  decisively oversized current turn.

- Deleted
  `src/copenet/host/frontend/tests/wsClientNormalization.test.ts`'s ordinary
  prose identity case. Retained the structured-looking compatibility case,
  which is the input most likely to be accidentally parsed or rewritten and
  therefore subsumes the plain-string identity risk.

- Deleted `personaHomeStore.test.ts` and `workspaceIntelStore.test.ts`. Both
  invoked direct Zustand setters and immediately read the assigned object back;
  neither covered normalization, persistence, merging, session isolation, or a
  consumer. Other store tests protecting meaningful isolation and state
  reconciliation remain.

### Consolidations

- Replaced three separate session Access examples with
  `test_session_access_reconciles_to_operator_requested_mode`, parameterized
  with descriptive IDs for default-to-full-access, default continuation, and
  full-access-to-default. All prior input transitions remain represented.

- Folded the `context.prepare` retired identifier into
  `test_tool_registry_does_not_expose_removed_experimental_tools` alongside
  `patch.plan` and `tools.describe`. This keeps one current-manifest contract at
  the `ToolRegistry` boundary instead of separate historical-phase checks.

- Removed four tests for
  `getConversationDebugHelperText`, `getWorkingSetSectionLabel`,
  `shouldUseWorkingSetCompactGrid`, and
  `shouldCollapseWorkingSetByDefault` after repository-wide search found no
  callers outside their definitions and tests. The four dead exports were
  removed in the same isolated frontend change. Tests and production helpers
  for the still-used action labels remain.

### Naming and deterministic infrastructure

- Renamed the synthetic Market scenario test to
  `test_scenario_metadata_exposes_configured_synthetic_shock_details`; its
  assertions are unchanged.

- Updated in-process integration module descriptions that called themselves
  end-to-end, and removed stale phase/inversion wording from tests edited in
  this pass. No test directories or large files moved.

- Changed
  `test_frontend_public_images_are_served_when_present` to monkeypatch
  `copenet.host.api._FRONTEND_DIST_DIR` to a `tmp_path` fixture. It no longer
  creates or mutates `frontend/dist/imgs/wallpaper.png`.

- Replaced the fixed 200ms sleep in
  `test_chat_run_survives_websocket_disconnect_after_started_response` with
  10ms polling of the public `chat.history` RPC, bounded by a monotonic
  two-second deadline with the last observed history in the failure message.

## Strengthened guarantees

### Tool-step cap

Each of the prompted, native Chat Completions, and OpenAI Responses contract
rows presents `MAX_TOOL_STEPS + 1` tool requests in one provider response. Each
row asserts:

- the loop interpreted 101 attempted calls;
- exactly `MAX_TOOL_STEPS` executor invocations and result events occurred;
- the completed turn records `toolCallCount == MAX_TOOL_STEPS`;
- `terminalReason == "max_turns"`;
- the user-visible cap explanation is emitted;
- exactly one final event terminates the stream.

This exposed a real defect: `MAX_TOOL_STEPS` bounded provider rounds, but every
parallel call inside a response was executed, so one response could exceed the
advertised tool-call cap. A shared bounding helper now truncates each received
batch to the remaining per-turn budget before calls are advertised or executed.

### Malformed RPC parameters

The malformed `chat.history(limit="lol")` test now proves exact error
classification, request correlation, useful diagnostic content, and continued
dispatch availability. Production already returned the correct
`INVALID_REQUEST` frame, so no RPC production change was needed.

## Deferred findings

- The Market no-lookahead test remains untouched because this pass did not add a
  correct point-in-time replacement.
- The two stale-run recovery tests remain separate: one proves cleanup reporting
  and idempotent sweeps, while the other proves a future send is unblocked.
  Combining them would obscure distinct failures.
- Shell command tables, OpenAI Responses parser variants, and frontend diff,
  tokenizer, truncation, and preview cases were left unchanged. They are
  possible later consolidations, but were not needed for this modest pass.
- Phase-era filenames were not moved. Only misleading names, module
  descriptions, comments, and docstrings in touched areas were corrected to
  avoid unnecessary file churn.
- The intentional Market, parser, policy, execution, approval, and transport
  defense-in-depth tests remain.
- No architectural, schema, persistence, browser-E2E, reconnect-approval, or
  provider-catalog work was attempted.

## Validation

Focused commands:

```text
uv run --extra dev pytest -q tests/integration/test_tool_loop_cap_contract.py
3 passed in 0.05s

uv run --extra dev pytest -q tests/integration/test_tool_loop_cap_contract.py tests/integration/test_phase_minus_1_baseline.py::test_dispatch_rpc_returns_invalid_request_on_bad_param tests/integration/test_phase_0_quickwins.py
11 passed in 0.07s

uv run --extra dev pytest -q tests/unit/test_workspace_intel_tools.py tests/integration/test_phase_minus_1_baseline.py tests/unit/test_build_chat_messages.py tests/unit/test_context_budget.py tests/integration/test_orchestrator.py
51 passed in 0.60s

uv run --extra dev pytest -q tests/unit/test_session_store.py tests/unit/test_tool_contracts.py tests/integration/test_phase_0_quickwins.py tests/unit/test_market_backtester.py tests/integration/test_multiturn_responses_e2e.py tests/integration/test_approval_gate.py tests/integration/test_phase_minus_1_baseline.py
61 passed in 0.50s

uv run --extra dev pytest -q tests/integration/test_app_api_agents.py::test_frontend_public_images_are_served_when_present
1 passed in 0.06s

for run_index in 1 2 3 4 5; do uv run --extra dev pytest -q tests/integration/test_ws_rpc.py::test_chat_run_survives_websocket_disconnect_after_started_response || exit 1; done
5/5 runs passed (0.11s to 0.14s each)
```

Complete suites and repository checks:

```text
/usr/bin/time -p uv run --extra dev pytest -q
703 passed in 27.29s
real 28.12

/usr/bin/time -p npm test
90 passed, 0 failed
duration_ms 1092.74675
real 1.35

npm run lint
tsc --noEmit: passed

npm run build
vite build: passed in 1.84s

python3 -m py_compile $(rg --files src/copenet -g '*.py')
passed

git diff --check
passed
```

The frontend build retained its pre-existing dynamic-import and large-chunk
warnings; it introduced no lint, type, test, or build failures.

## Commits

The pass was recorded in these local commits:

1. `8f89764 test: strengthen and simplify audited runtime coverage`
2. `784d532 test(frontend): remove verified low-value coverage`
3. `677efd1 docs: record test suite audit and cleanup pass`
4. `docs: normalize test report formatting`
