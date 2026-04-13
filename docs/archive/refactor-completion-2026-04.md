# CopeNet Refactor Completion Notes

This note archives the architecture cleanup work that moved CopeNet out of the large-file, duplicate-path, defensive-slop phase and into a stable backend base for the next product phase.

## What Landed

- Boundary cleanup:
  - session storage is snake_case on disk
  - transcript storage is snake_case on disk and converted to camelCase only at the public boundary
  - RPC handlers normalize once and pass clean internal shapes inward
  - `GatewayClient._rpc()` is the trust boundary for non-streaming responses
- Core consolidation:
  - orchestration, harness, sessions, tools, and tracing live under `src/copenet/core/`
  - legacy shim and duplicate pre-core paths were removed
- Tool runtime cleanup:
  - builtin readonly tools were split into handler modules by concern
  - tool loop behavior is covered by integration tests
- Frontend cleanup:
  - the vanilla UI was split into ES modules
  - DOM ownership moved out of `state.js`
  - browser-side error handling no longer hides failures with empty catches
  - auth token lookup is explicit in the frontend
- Test coverage:
  - unit tests cover session storage, transcript storage, and tool contracts
  - integration tests cover orchestrator flow and prompted tool-loop behavior

## Validation Performed

- Python compile pass
- frontend JS syntax checks
- pytest suite with unit and integration coverage
- server startup smoke via `uv run copenet`
- live tool-call validation against Codex and LM Studio flows during manual use

## Remaining Work Moved Out Of Refactor

The remaining work is no longer “finish the refactor.” It is now standard product/backlog work and lives in `TODO.md`.

Main promoted items:

- archived-session resurfacing/restore UX
- auth hardening decision
- provider metadata cleanup in the harness/provider boundary
- deeper websocket/RPC integration coverage
- React frontend migration

## Outcome

The backend is now in a stable-enough state to design and build the new frontend against it without dragging old architectural cleanup along for the ride.
