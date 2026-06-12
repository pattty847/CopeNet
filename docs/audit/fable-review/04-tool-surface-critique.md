# Tool Surface Critique

Evaluated from the model's seat: descriptors as the model reads them, handlers as they actually behave.

## Baseline correction

The live manifest is **not** the 8 tools described in CLAUDE.md-era docs. `MANIFEST_TOOL_IDS` (`builtin_readonly.py:29-38`) is: `files.read`, `files.write`, `files.edit`, `files.rg`, `shell.exec`, `plan.write`, `web.search`, `web.fetch`. `context.prepare` was retired in Phase 0.3 (`builtin_readonly.py:18`); `artifact.create` is registered but deferred out of the manifest. Any doc still describing the old set should be updated.

## shell.exec policy — the serious findings

### HIGH: `find` write predicates punch through the "read-only" allowlist
`policy.py:19` allowlists `find`; the check is `argv[0] not in allowlist` (`shell.py:240`). So in guarded mode:
- `find . -name "*.pyc" -delete` — deletes files.
- `find . -exec rm {} +` — runs arbitrary `rm` (the `+` form contains no `;`, so chain-splitting never sees it; the `\;` form is blocked only by accident — the trailing backslash breaks shlex).

Guarded mode can delete the workspace. Fix: reject `find` argv containing `-delete`, `-exec`, `-execdir`, `-ok`, `-okdir`, `-fprint*`.

### MEDIUM-HIGH: writable flags on safelisted git subcommands
`shell.py:49-58` safelists `branch` by subcommand name only: `git branch -D main` deletes a branch; `git branch -m` mutates refs. (Leading global flags like `git -c …` happen to fail safe — `argv[1]` isn't a known subcommand.) Fix: drop `branch` from the read safelist or reject write flags on it.

### MEDIUM: the full-access approval gate is substring-matched — both bypassable and over-broad
`_approval_required` (`shell.py:154-156`) lowercases the raw command and does `pattern in normalized` against patterns like `"sudo"`, `"curl "`. Bypassable: `curl` followed by a tab instead of a space dodges `"curl "`. Over-broad: any command merely *containing* `"git reset"` (e.g. in a commit message) trips the gate, and `/usr/bin/sudo` vs `sudoedit` are treated identically. Fix: tokenize and match on argv basename + flags, not substrings.

### MEDIUM: scope metadata only checks the last path token
`_shell_access_metadata` (`shell.py:130-136`) labels workspace scope from the **last** path-like arg, so `head ~/.ssh/id_rsa ./local` reports `inside_workspace` while reading outside. Reads outside the workspace are allowed-by-design in guarded mode ("roaming"), but the label — the thing the operator sees — is wrong. Fix: scope-check every path token.

### Smaller edge cases
- `||` is not split by `_CHAIN_SPLIT_RE` (`shell.py:24` handles `&&`/`;` only) — it survives into argv as a literal token. Usually harmless; occasionally surprising. Subshells `$(...)`/backticks fail safe: `subprocess.run(argv)` without a shell (`_shared.py:21-29`) never evaluates them.
- The `_HARD_BLOCKED_TOKENS` check is a substring scan over the raw string including inside quotes: `rg "a|b"` — regex alternation, a routine pattern — is wrongly blocked. Tokenize before checking.
- `cd subdir && rg foo` is blocked because `cd` isn't allowlisted; models try this constantly. Document the workdir convention in the descriptor or special-case `cd`.
- Legitimate read-only pipes (`git log | head`) are blocked in guarded mode. Documented tradeoff, but it pushes models toward full-access.

### The descriptor contradicts the handler
The description says "Default modes allow **one** read-only allowlisted command" (`shell.py:33-34`) and the prompted-lane system prompt says "Do not use pipes, chaining, redirection, or multiple commands" (`tool_loop.py:793`) — but the handler supports `&&`/`;` chains of allowlisted commands (`shell.py:233-235`). A model that believes the descriptor under-uses the tool; a full-access model in the prompted lane is told not to pipe when it can. Rewrite both to be mode-aware.

### What's right
The guarded/full-access switch itself is clean (`policy.py:52-63`), and **approval-required proposals genuinely resume**: `_make_approval_gated_executor` (`runtime.py:39-91`) parks the run, and on approve seeds `approved_commands` so the exact command re-runs (`shell.py:151-153`). Verified end-to-end. Caveat: it only works when `emit_event` is present — CLI/headless runs get the blocked result with no approval path.

## files.* — mostly good, with sharp edges

- **files.read descriptor is genuinely good** — line + char modes explained, rg→read workflow spelled out, truncation messages embed the exact continuation call (`files.py:236-238`).
- **MEDIUM: the error message recommends tools that don't exist.** `files.py:136-138`: "use files.list to inspect directories or files.search to search inside them" — neither is registered; a model following this gets `unknown tool`. Change to `shell.exec ls` / `files.rg`.
- **MEDIUM: out-of-range line reads succeed silently.** `files.py:212-216` clamps `end = min(total, max(start, end))`, so `start_line=500` on a 100-line file returns `ok=True` with empty content and summary "Read file X lines 500-100." A model will conclude the region is empty. Error or clamp-and-say-so.
- **MEDIUM: `files.rg context_lines` is advertised, slows the search, and returns nothing.** The flag is passed to rg (`files.py:287-288`) but the JSON parser keeps only `type=="match"` events (`files.py:315-316`) — context lines are dropped. Collect them or delete the parameter.
- `pattern` and `path` are not marked `required` in their schemas (`files.py:30-39,53-61`) though handlers raise without them. Add `"required"`.
- Patterns starting with `-` break `files.rg` (no `--`/`-e` separator before the pattern, `files.py:286-289`).
- `files.rg` snippets silently truncate at 240 chars (`files.py:339`) with no marker.
- **files.edit is well-designed**: occurrence counting with replace_all-or-disambiguate, bounded diff feedback, digest stale-write guard — and partial reads still digest the full file (`files.py:145`) so the digest contract round-trips correctly. No findings.
- files.write: no read-before-write nudge and no atomic temp+rename (`files.py:380-382`). Low for a single-user tool, but cheap to fix.
- Binary files: `files.read` opens with `errors="replace"` (`files.py:141`) — a PNG returns mojibake rather than a structured "binary file" signal.

## plan.write — cosmetic by design; say so

The descriptor is excellent (full-plan-each-time, one in_progress — TodoWrite discipline). But the handler does **not** write to `TurnState` (`turn_state.py` has no plan field; `plan.write` falls through to generic evidence category at `:150`), and nothing downstream — harness decisions, finalization, policy — reads the plan. It reaches the UI purely as a tool-result preview (`contracts.py:304-313` → `PlanView`). It IS called in live traces, so it works as an observability checklist. Fine if intentional; if the plan is ever meant to gate finalization ("did you complete what you said?"), it needs to land on TurnState first. One flaw: malformed entries are silently dropped/coerced (`plan.py:27-35`) with no warning in the result.

## artifact.create — fully wired, permanently dark

The injection chain is complete: `runtime.py:308,319,322` pass `session_key`, `artifact_store`, `run_id` into `ToolExecutionContext`, and the handler guards on exactly those (`artifacts.py:34`). But the tool is absent from `MANIFEST_TOOL_IDS`, and `list_tools()` filters to the manifest (`registry.py:36-40`) — the model can never call it. Zero `tool_requested` traces for it exist; the `artifact_created` events in run logs are the orchestrator's own answer-persistence path (`runtime.py:482-505`). Meanwhile the **auto-artifact path is the live mechanism and it's sound**: tool results >4000 chars are persisted via `_materialize_tool_result_artifact` (`tool_loop.py:892-960`). Decide: put it in the manifest or delete the handler in the Phase 5 sweep — a fully-built dark tool is the worst of both.

## Capability gaps

- **Find-file-by-name** is awkward: `files.rg` searches contents; the clean paths are `shell.exec find -name` (the same binary with the `-delete` hole) or `rg --files | rg name` (blocked — pipe). A `files.glob` primitive or an `rg --files` mode would close it.
- **No long-running processes** — 5s guarded / 120s full-access timeout, no background runs. Probably intentional for a turn-based agent; becomes a gap the moment "run the dev server" is a product goal.
- Directory listing is covered (`ls` is allowlisted) but mis-advertised by the dead `files.list` hint above.
- URL access is covered (`web.search`/`web.fetch` are in the manifest).

## registry repeat-detection — safe (positive)

Signature = full `{toolId, arguments}` JSON (`registry.py:193-207`), so reading the same file with different ranges never trips it; only byte-identical calls warn at 3 and block at 4. Correct anti-loop design. The real gap is coverage, not false positives: enforcement lives only in `files.read`/`files.rg` (`files.py:121-134,261-274`) — a model looping `shell.exec git status` forever is never warned (see `06-harness-transparency-gaps.md` §4).
