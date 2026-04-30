# Gemini Probe: Cross-Provider Harness / Tooling Investigation

Use this prompt with Gemini 1.5 Pro / 2.5 Pro or another long-context model. The goal is to deeply inspect CopeNet's live probe bundles, traces, transcripts, and relevant source files, then tell us **exactly where the failure pattern is coming from**.

---

You are investigating CopeNet, a local agent gateway / harness project. Your job is to read the attached code, probe bundles, traces, transcripts, and run records, then produce a **forensic diagnosis** of why provider/model behavior differs so much across LM Studio local models and Codex CLI.

## What CopeNet is

CopeNet is a local agent gateway with:
- a FastAPI + WebSocket host
- provider adapters for `codex-cli`, `lm-studio`, and `ollama`
- a harness layer that plans tool use, runs tool loops, records evidence, and applies final-answer gating
- a live probe runner that executes the same test prompts against different providers/models and writes bundle artifacts

The current investigation is about **multi-tool behavior, premature stopping, grounding, final-gate recovery, and suspicious provider/model differences**.

## What we suspect

We do **not** want a vague summary. We want you to decide, based on evidence, which of these is most likely true:

1. The CopeNet harness/controller has a real control-flow bug.
2. CopeNet’s interface/protocol with one or more providers is subtly wrong.
3. The local models are behaving differently because of model-specific tool-use quirks.
4. Probe classification is overstating or mislabeling some behaviors.
5. More than one of the above is true.

We suspect there may be a **small but important bug** rather than the whole harness being conceptually broken.

## Main question

After reading all attached materials, answer:

**What is the smallest set of concrete root causes that best explain the observed cross-provider behavior?**

We care especially about:
- why Codex `gpt-5.4` is showing so many `partial_tool_success_with_block` outcomes when the same model performs beautifully in other agent harnesses
- why Qwen is producing many `rejected_final_then_recovered` results plus several `runtime_error`s
- why Gemma/Unsloth variants appear partly successful but still show some odd grounding/finalization failures
- whether CopeNet is incorrectly interpreting provider outputs, tool loop steps, blocked results, or final candidates

## Important context about the trace / bundle structure

Each probe bundle directory typically contains:
- `summary.json`
- `report.md`
- one subdirectory per run containing:
  - `run_record.json`
  - `trace.jsonl`
  - `transcript.md`
  - `transcript.json`
  - `final_payload.json`
  - `session_state.json`
  - `notes.json`
  - `artifacts.json`
  - `probe.json`

### Key trace events

From `docs/TRACING.md`, relevant events include:
- `harness_planned`
- `provider_turn_started`
- `provider_turn_completed`
- `tool_requested`
- `tool_executed`
- `tool_blocked`
- `final_gate_rejected`
- `assistant_finalized`
- `run_failed`
- `run_completed`

### Important concepts

- `willAttemptToolLoop`: whether the harness planned a tool loop
- `toolExecutionMode`: whether the run used native tools vs prompted tool use
- `taskContract`: contract inferred for the run
- `evidenceLedger`: compact execution truth tracked across steps
- `classification`: bundle-level label like:
  - `batch_success`
  - `rejected_final_then_recovered`
  - `partial_tool_success_with_block`
  - `ungrounded_repo_answer`
  - `premature_stop_after_one_tool`
  - `runtime_error`
  - `blocked_but_recovered`

## Specific things to check

### 1. Is CopeNet using the same protocol shape across providers in a way that harms some of them?
Check whether:
- Codex CLI is being treated as native tool calling but is still effectively being made to speak CopeNet’s custom final-candidate JSON dialect
- LM Studio models are using native provider tool calls vs prompted tool use consistently
- provider request/response handling differs in a way that could explain the results

### 2. Is final gating behaving incorrectly at the end of the loop?
Check whether:
- the harness rejects an invalid final candidate and then still allows a final answer without the contract actually being satisfied
- step-budget exhaustion or terminal loop conditions allow ungrounded finals to pass
- some classifications are produced even when the trace suggests the contract remained unsatisfied

### 3. Are tool blocks expected, or are they artifacts of our own anti-repeat logic / policy?
Check whether:
- `partial_tool_success_with_block` on Codex is mostly due to our anti-repeat protections
- the blocks are legitimate (same exact tool call spam) vs a sign we are being too strict or too literal
- the block occurs because the model is repeating shallow reconnaissance, or because our interface is steering it into a bad action pattern

### 4. Are runtime errors coming from model behavior, provider parsing, or loop semantics?
Especially for Qwen, determine whether runtime errors come from:
- provider/model timeout or malformed output
- loop control logic
- parsing of tool calls or final candidates
- repeated gate rejection without a valid continuation path
- other provider-side failures

### 5. Are the classifications honest?
Check whether the labels in `summary.json` / `report.md` match the underlying traces. Call out any mismatches.

### 6. Compare good vs bad traces directly
Find at least:
- one relatively healthy Unsloth run
- one suspicious Codex run
- one Qwen runtime error run
- one Google Gemma run

Then compare:
- tool sequence
- trace sequence
- gate behavior
- finalization behavior
- transcript content
- whether the final answer truly reflects the evidence gathered

## Files and directories to inspect

### Source / docs
Please read these first so you understand CopeNet’s control flow and trace format:
- `/Users/copeharder/Programming/CopeNet/docs/TRACING.md`
- `/Users/copeharder/Programming/CopeNet/scripts/live_probe_matrix.py`
- `/Users/copeharder/Programming/CopeNet/src/copenet/probes/runtime_bundle.py`
- `/Users/copeharder/Programming/CopeNet/src/copenet/core/harness/tool_loop.py`
- `/Users/copeharder/Programming/CopeNet/src/copenet/core/harness/final_gate.py`
- `/Users/copeharder/Programming/CopeNet/src/copenet/core/harness/planning.py`
- `/Users/copeharder/Programming/CopeNet/src/copenet/core/runtime/turn_state.py`
- `/Users/copeharder/Programming/CopeNet/src/copenet/providers/local_http.py`
- `/Users/copeharder/Programming/CopeNet/src/copenet/providers/codex_cli.py`
- `/Users/copeharder/Programming/CopeNet/src/copenet/core/tools/handlers/files.py`

### Probe bundles to inspect
Read all relevant files under these bundle roots:
- Google Gemma 4 E4B: `/Users/copeharder/Programming/CopeNet/tmp/probe_runs/20260428T040739Z`
- Unsloth Gemma 4 E4B IT: `/Users/copeharder/Programming/CopeNet/tmp/probe_runs/20260428T042410Z`
- Codex GPT-5.4: `/Users/copeharder/Programming/CopeNet/tmp/probe_runs/20260428T045548Z`
- Qwen 3.5 9B: `/Users/copeharder/Programming/CopeNet/tmp/probe_runs/20260428T051149Z`

If needed for additional comparison, you may also inspect:
- earlier Codex failure bundle before server restart: `/Users/copeharder/Programming/CopeNet/tmp/probe_runs/20260428T044653Z`
- earlier Gemma run for comparison: `/Users/copeharder/Programming/CopeNet/tmp/probe_runs/20260427T063223Z`

## Known observed outcomes

### Google Gemma 4 E4B
Key pattern:
- many `batch_success`
- some remaining `ungrounded_repo_answer`
- suspicious repeated reconnaissance / listing behavior

### Unsloth Gemma 4 E4B IT
Key pattern:
- generally healthier than plain Gemma 4 E4B
- several `rejected_final_then_recovered`
- still `patch_verify_probe: ungrounded_repo_answer`

### Codex GPT-5.4
Key pattern:
- many `partial_tool_success_with_block`
- one `batch_success`
- one `premature_stop_after_one_tool`
- this is suspicious because Codex performs much better in other harnesses like OpenClaw

### Qwen 3.5 9B
Key pattern:
- many `rejected_final_then_recovered`
- several `runtime_error`s
- long runtimes and many steps
- this may reflect a provider/interface issue, loop issue, or a model-specific failure mode

## Deliverable format

Give your answer in exactly this structure:

### 1. Executive diagnosis
A short answer to: what are the most likely root causes?

### 2. Confirmed findings
Bullet list of things you can prove from the logs/traces/code.
For each finding, cite specific files and run directories.

### 3. Inferred findings
Bullet list of likely conclusions that are not 100% proven but strongly supported.
Mark confidence per item.

### 4. Cross-provider comparison table
A compact matrix comparing:
- Google Gemma 4 E4B
- Unsloth Gemma 4 E4B IT
- Codex GPT-5.4
- Qwen 3.5 9B

Include:
- tool protocol path
- common tool sequence shape
- common failure mode
- gate behavior
- whether the problem appears model-side, harness-side, provider-side, or mixed

### 5. Most likely bug(s)
If you think there is a small hilarious bug, say exactly what it probably is and where it probably lives.
Point to concrete files/functions.

### 6. Recommended next instrumentation
Tell us exactly what extra trace/log events to add so the next run removes ambiguity.
Keep this targeted and minimal.

### 7. Recommended next experiments
Give a short prioritized list of experiments or code checks to run next.
These should be concrete and ordered.

## Critical instructions

- Separate **confirmed by evidence** from **inference**.
- Do not give generic agent-harness advice.
- Do not just summarize outcomes; explain the mechanism that likely produced them.
- If you think probe classification is part of the issue, say so explicitly.
- If you think the harness is mostly fine and the interface/protocol is the real issue, say that explicitly.
- If you think the harness has a real finalization bug, say that explicitly.
- Quote or cite specific run directories, trace events, and source files whenever possible.

