# Bootstrap Prompt

We are continuing a focused investigation into CopeNet's local-model harness behavior, starting from the current state below. Treat this as a serious harness-engineering study, not a casual repo browse.

## Mission

We want to learn from a real working agent harness, compare it to CopeNet, and turn those findings into concrete improvements for small local models.

Our core practical questions are:

- how do we stop local models from being confidently lazy?
- how do we force grounded continuation instead of early finalization?
- how do we keep answers tied to evidence rather than folder-name vibes?
- how do we help the model choose the right tools in the right order?

## CopeNet Context

CopeNet is a local agent gateway with:

- FastAPI + WebSocket host
- pluggable providers for Codex CLI, LM Studio, and Ollama
- persisted sessions, transcripts, run records, and traces
- a CopeNet-native harness layer
- built-in repo/file/context tools

Relevant harness files currently include:

- `/Users/copeharder/Programming/CopeNet/src/copenet/core/harness/planning.py`
- `/Users/copeharder/Programming/CopeNet/src/copenet/core/harness/tool_loop.py`
- `/Users/copeharder/Programming/CopeNet/src/copenet/core/harness/final_gate.py`
- `/Users/copeharder/Programming/CopeNet/src/copenet/core/runtime/turn_state.py`
- `/Users/copeharder/Programming/CopeNet/src/copenet/providers/local_http.py`
- `/Users/copeharder/Programming/CopeNet/src/copenet/probes/runtime_bundle.py`

## What We Already Built

We already added:

- task contracts
- evidence ledger / turn state
- final gate
- stronger probe suite
- LM Studio native OpenAI-style tool calling
- native-vs-prompted tool protocol tracking in probe output

The native LM Studio path was the right move because Gemma 4 was trained for tool calling, and CopeNet previously forced it through a custom prompted JSON dialect instead of its native tool protocol.

## What We Learned From Gemma 4

Using `google/gemma-4-e4b` through LM Studio:

- moving to native tool calls helped
- same-session behavior improved
- final-gate rejection/recovery is now observable in live runs
- but Gemma still often uses the wrong tools

Current failure pattern:

- repeated `files.list`
- little or no `files.read`
- sometimes `context.prepare` is treated like stronger grounding than it should be
- final answers may still be ungrounded despite legal tool usage

In other words:

- tool syntax improved
- tool judgment is still weak

## Latest Live Result Summary

The latest probe run against Gemma 4 E4B showed:

- native tool protocol is active
- `relevant_files_bug_probe` reached `rejected_final_then_recovered`
- but several probes still hit `ungrounded_repo_answer`

Representative bad cases:

- `patch_plan_probe`
  - mostly `context.prepare` + repeated `files.list`
  - no meaningful file reads
- `artifact_dependency_probe`
  - `files.list` over and over
  - no real grounding
- `same_session_seed_probe`
  - same repeated-listing pattern

Representative bundle root:

- `/Users/copeharder/Programming/CopeNet/tmp/probe_runs/20260427T063223Z`

Useful files from that run:

- `/Users/copeharder/Programming/CopeNet/tmp/probe_runs/20260427T063223Z/summary.json`
- `/Users/copeharder/Programming/CopeNet/tmp/probe_runs/20260427T063223Z/report.md`

## Current Hypothesis

We have probably solved the wrong layer first and now need to focus on **tool-choice policy**.

The likely next issues are:

- repeated reconnaissance is too cheap
- `files.list` saturation is not punished hard enough
- `context.prepare` may count as grounding too easily for repo/code tasks
- the harness still doesn't push the model strongly enough toward:
  - `files.read`
  - `files.search`
  - evidence-bearing follow-up actions

## Investigation Requirements

Please work like a harness engineer.

Do not just summarize the reference project. Instead:

1. trace its actual execution loop
2. identify how it chooses, constrains, and sequences tools
3. inspect how it handles:
   - planning
   - retries
   - continuation
   - evidence
   - finalization
   - memory / state
   - same-session behavior
4. compare each relevant mechanism to CopeNet
5. record exact pain points and exact differences
6. propose changes only after we can point to what the reference harness is doing better

## Sub-Agent Instructions

Use sub-agents aggressively for this investigation when allowed.

Ideal delegation pattern:

1. one agent maps the reference harness architecture
2. one agent traces its tool loop / controller logic
3. one agent studies continuation / retry / finalization behavior
4. one agent compares those findings against CopeNet's current harness files

Each sub-agent should own a distinct read scope and return:

- touched files
- exact mechanism found
- why it matters
- likely relevance to CopeNet

## Documentation Discipline

Keep notes under:

- `/Users/copeharder/Programming/CopeNet/docs/investigations/hermes-harness/`

Use:

- `NOTES.md` for raw findings
- `COMPARE.md` for side-by-side mechanism comparisons
- `TODO.md` for the evolving checklist
- `scratch/` and `raw/` for temporary copied snippets and dumps

Record:

- what we observed
- what we think it means
- what remains uncertain
- which claims are confirmed by code
- which claims are still inference

## Immediate First Steps

1. inspect the reference harness repo structure
2. locate its main agent loop / controller / provider integration files
3. identify how tools are surfaced and how continuation is enforced
4. compare that directly to:
   - `/Users/copeharder/Programming/CopeNet/src/copenet/core/harness/tool_loop.py`
   - `/Users/copeharder/Programming/CopeNet/src/copenet/core/harness/planning.py`
   - `/Users/copeharder/Programming/CopeNet/src/copenet/providers/local_http.py`
5. write down the first 3 precise gaps before proposing a patch

## Important Reminder

Our goal is not to copy another project blindly.

Our goal is to learn:

- what works
- why it works
- which parts are generally reusable
- which parts are specific to their runtime or product shape

Then we bring back only the pieces that actually solve CopeNet's failures.
