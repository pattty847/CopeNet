# CopeNet Finishing Touches

This document is the short list for the cleanup pass after the big structural refactor. The frontend split, `core/` consolidation, and standards updates already landed. What remains now is the work that makes the repo actually feel finished and consistently organized.

## What Is Already Done

- `app.js` is now bootstrap-only and the browser app is split into ES modules.
- Core runtime code moved under `src/copenet/core/`.
- Contributor standards were updated to enforce boundary validation and extraction discipline.
- The refactor planning docs now live under `docs/refactor/`.

## Repo Standard For Naming

We should standardize the boundary, not force one style into both languages.

| Layer | Format |
|---|---|
| Python code | `snake_case` |
| JavaScript code | `camelCase` |
| RPC / browser payloads | `camelCase` |
| Disk storage (`index.json`, transcript JSONL) | `snake_case` |

Rule: normalize once at the boundary, then trust the normalized shape downstream.

That means:

- the host RPC layer should own `camelCase` to `snake_case` conversion;
- storage loaders should read the storage format they actually own;
- internal Python flows should stop re-checking already-normalized values.

## Remaining Work

### 1. Finish the naming and normalization cleanup

This is the highest-priority cleanup because it removes the biggest source of architectural ambiguity.

- `src/copenet/core/sessions/session_store.py` still accepts both `snake_case` and `camelCase` fields in `SessionIndexEntry.from_json()`, even though disk storage is snake_case.
- `src/copenet/host/rpc_chat.py` still performs repeated field coercion instead of normalizing once and passing a clean DTO inward.
- `src/copenet/client.py` still re-checks payload shapes after `_rpc()` instead of making `_rpc()` the real trust boundary.

Target outcome:

- storage deserialization is snake_case only;
- wire payloads stay camelCase;
- the host RPC boundary is the only place that translates between them.

### 2. Remove leftover legacy compatibility layers

If we are serious about not keeping backward compatibility forever, we should stop carrying old structures once the imports are updated.

Current leftovers:

- `src/copenet/tools/builtin_readonly.py` still duplicates `src/copenet/core/tools/builtin_readonly.py`
- `src/copenet/tools/registry.py` still duplicates `src/copenet/core/tools/registry.py`
- top-level shim modules such as `src/copenet/orchestrator.py` and `src/copenet/sessions/session_store.py` still exist to preserve old imports

Target outcome:

- keep one implementation path under `src/copenet/core/`;
- remove duplicate pre-core implementations;
- delete shims once the repo is internally migrated.

### 3. Split `core/tools/builtin_readonly.py`

`src/copenet/core/tools/builtin_readonly.py` is still 359 lines and mixes context, file, git, and shell handlers in one file.

Recommended structure:

```text
src/copenet/core/tools/
├── handlers/
│   ├── __init__.py
│   ├── context.py
│   ├── files.py
│   ├── git.py
│   └── shell.py
└── builtin_readonly.py
```

`builtin_readonly.py` should become an aggregator only.

### 4. Clean up `state.js`

The frontend split landed, but `src/copenet/host/static/js/state.js` still does too much.

- it owns a large set of DOM references;
- it exports `TOKEN = 'dev-token'` in browser code;
- it mixes state storage with UI wiring concerns.

Target outcome:

- `state.js` owns shared state and simple selectors only;
- DOM querying lives in controllers and render modules;
- dev token behavior is explicit and not baked into frontend state.

### 5. Replace silent UI catches with observable handling

Several browser paths still use `catch (_) {}` and hide failures:

- `src/copenet/host/static/js/controllers/chat.js`
- `src/copenet/host/static/js/controllers/sessions.js`
- `src/copenet/host/static/js/render/messages.js`

Target outcome:

- expected cleanup failures can stay quiet only when intentional and documented;
- unexpected errors should at least log, banner, or trace visibly.

### 6. Make providers injectable in `Orchestrator`

`src/copenet/core/orchestrator/__init__.py` still constructs providers directly in `__init__`.

Target outcome:

- add an optional `providers` parameter;
- skip default provider construction when it is supplied;
- make orchestrator tests independent of real runtimes.

### 7. Add the first real tests

There is still no `tests/` tree and no pytest setup in `pyproject.toml`.

Minimum useful first pass:

- session store tests against real temp dirs
- transcript store tests
- tool contract tests
- orchestrator integration tests with a fake provider

## Recommended Execution Order

1. Finish naming and normalization cleanup.
2. Remove legacy duplicate implementations and shims we no longer want.
3. Split `core/tools/builtin_readonly.py`.
4. Clean up `state.js` and the browser token path.
5. Replace silent catches.
6. Add provider injection and tests.

## Verification

Use this baseline after each cleanup slice:

```bash
python3 -m py_compile $(rg --files src/copenet -g '*.py')
node --check src/copenet/host/static/app.js
node --check $(rg --files src/copenet/host/static/js -g '*.js')
uv run cope
```
