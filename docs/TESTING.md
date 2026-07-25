# Testing Runbook

Keep the safety checks layered so we can run the lightest thing that proves the change.

Recommended order:

1. Compile / syntax check
   - `python3 -m py_compile $(rg --files src/copenet tests -g '*.py')`
2. Backend unit + integration suite
   - `uv run --extra dev pytest -q`
3. Frontend typecheck + unit/render tests
   - `cd src/copenet/host/frontend && npm run lint && npm test`
4. WebSocket / RPC transport suite
   - `uv run --extra dev pytest -q tests/integration/test_ws_rpc.py`
5. Manual app smoke
   - use this when touching behavior the current test suite does not yet cover, especially UI flows

Suggested usage:

- Run the compile check first after any backend edit.
- Run `tests/integration/test_ws_rpc.py` when touching WebSocket, RPC, session transport, or chat event shapes.
- Run the full pytest suite before committing backend changes.
- Use manual browser smoke for final confidence, not as the first line of regression detection.

Current suite weight:

- compile check: very fast
- full pytest suite: small and local-machine friendly
- RPC transport suite: intentionally compact and sequential

Current RPC transport coverage:

- connect handshake success/failure
- providers/models/tools catalog methods
- sessions create/list/resolve/archive behavior
- empty history and persisted history
- chat send streaming over WebSocket
- chat abort
- tool execution metadata on public chat events

Browser validation is part of the final safety loop for affected interaction flows,
but it does not replace deterministic lint, unit, render, and integration checks.

## Live Provider Probe Runner

For real-model behavior, use the live probe runner instead of pytest:

- start CopeNet with tracing enabled:
  - `COPNET_TRACE=1 uv run copenet`
- run the probe matrix:
  - `uv run python scripts/live_probe_matrix.py --lm-model <your-lm-studio-model>`
- run a focused local-model sweep across LM Studio chat models:
  - `uv run python scripts/lmstudio_probe_sweep.py --limit 3`
- compare available frontier lanes on the same focused probes:
  - `uv run python scripts/live_probe_matrix.py --providers openai-codex,claude-cli --probes repo_inspect_summary,patch_plan_probe`

What it does:

- probes `openai-codex` plus one LM Studio model by default
- runs a compact tool-use matrix in mostly fresh sessions
- includes one deliberate same-session follow-up pair to expose resume drift
- writes a JSON artifact under `tmp/live_probe_results/`
- prints a compact terminal summary for quick comparison

What it is for:

- real provider/model compliance testing
- tool-use drift and prose-fallback diagnosis
- comparing the OAuth OpenAI Codex endpoint to one local model under CopeNet's harness
- separately sampling external harness lanes such as `codex-cli` and `claude-cli`
- short-context frontier-vs-local comparisons before deciding whether to tune the harness or wait for stronger local models

What it is not:

- deterministic CI coverage
- a replacement for the backend pytest suite


## LM Studio lifecycle smoke

Use this when you want a real local-runtime check for cold-load, reuse, model switching, chat, and unload behavior.

- gated by env var so it stays out of normal CI and regular pytest runs
- requires LM Studio local server mode to be running
- uses CopeNet's `LmStudioProvider`, not ad hoc HTTP calls, so it exercises the real integration path

Run it with:

- `COPNET_RUN_LM_STUDIO_SMOKE=1 uv run python scripts/lmstudio_smoke.py`
- if second-model switching is too slow on the current machine, use `COPNET_RUN_LM_STUDIO_SMOKE=1 uv run python scripts/lmstudio_smoke.py --skip-switch`

Useful overrides:

- `COPNET_LM_STUDIO_BASE_URL=http://127.0.0.1:1234`
- `COPNET_LM_STUDIO_SMOKE_MODEL=qwen/qwen3.5-9b`
- `COPNET_LM_STUDIO_SMOKE_SECONDARY_MODEL=google/gemma-4-e2b`
- `COPNET_LM_STUDIO_SMOKE_PROMPT='Say hello in one sentence.'`

Suggested verification order at home:

1. `python3 -m py_compile $(rg --files src/copenet tests scripts -g '*.py')`
2. `uv run --extra dev pytest -q tests/unit/test_lm_studio_provider.py tests/integration/test_app_api.py tests/integration/test_app_api_lm_studio.py`
3. `COPNET_RUN_LM_STUDIO_SMOKE=1 uv run python scripts/lmstudio_smoke.py`
4. optional full suite, `uv run --extra dev pytest -q`
