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
