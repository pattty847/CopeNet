# Testing Runbook

Keep the safety checks layered so we can run the lightest thing that proves the change.

Recommended order:

1. Compile / syntax check
   - `python3 -m py_compile $(rg --files src/copenet tests -g '*.py')`
2. Backend unit + integration suite
   - `uv run --extra dev pytest -q`
3. WebSocket / RPC transport suite
   - `uv run --extra dev pytest -q tests/integration/test_ws_rpc.py`
4. Manual app smoke
   - use this when touching behavior the current test suite does not yet cover, especially UI flows

Suggested usage while the React frontend is in flight:

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

Known gap kept out of this runbook on purpose:

- browser automation is not part of the default safety loop yet

## Live Provider Probe Runner

For real-model behavior, use the live probe runner instead of pytest:

- start CopeNet with tracing enabled:
  - `COPNET_TRACE=1 uv run copenet`
- run the probe matrix:
  - `uv run python scripts/live_probe_matrix.py --lm-model <your-lm-studio-model>`

What it does:

- probes `codex-cli` plus one LM Studio model by default
- runs a compact tool-use matrix in mostly fresh sessions
- includes one deliberate same-session follow-up pair to expose resume drift
- writes a JSON artifact under `tmp/live_probe_results/`
- prints a compact terminal summary for quick comparison

What it is for:

- real provider/model compliance testing
- tool-use drift and prose-fallback diagnosis
- comparing Codex behavior to one local model

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
