# Browser Agent Prototype

## Goal
Prototype a deterministic browser-control loop in CopeNet before porting the architecture into a first-class CopeNet browser capability and later into OpenClaw-facing workflows.

This is intentionally **not** a vibes-based browser-use stack.

The shape is:

```text
observe -> decide -> validate -> act -> trace -> observe
```

The model should choose **intent-level actions** against a controlled schema, not freestyle raw selectors.

## Status

### Phase 1 completed
- Playwright-backed Chromium session
- Structured page observer
- Stable element ids per observation pass
- Strict action validator
- JSONL trace recorder
- CLI demo entrypoint
- Screenshot artifact capture

### Phase 2 completed
- strict one-action JSON schema
- decision-provider abstraction
- scripted decision provider for deterministic demos/tests
- loop controller with max-step, stuck, and validation-failure stopping
- high-risk direct-action blocking
- richer per-step trace rows
- upgraded CLI task runner

### Phase 3 completed
- real provider-backed decision adapter
- one-shot repair retry for invalid provider JSON
- better element ranking so useful search inputs outrank junk
- page-change detection
- finish gate tied to visible evidence
- repeated failed action escalation to `ask_user`
- provider-backed CLI path for real public browsing tasks

## Module layout

- `src/copenet/browser_agent/models.py`
- `src/copenet/browser_agent/session.py`
- `src/copenet/browser_agent/observer.py`
- `src/copenet/browser_agent/validator.py`
- `src/copenet/browser_agent/decision.py`
- `src/copenet/browser_agent/loop.py`
- `src/copenet/browser_agent/trace.py`
- `src/copenet/browser_agent/cli.py`

## Install

```bash
cd /path/to/CopeNet
uv sync
uv run playwright install chromium
```

## CLI examples

### Provider-backed GitHub demo
```bash
uv run copenet-browser-demo \
  --provider copenet \
  --task "Search GitHub for CopeNet" \
  --start-url https://github.com \
  --max-steps 12
```

### Explicit local-model provider
```bash
uv run copenet-browser-demo \
  --provider lm-studio \
  --model google/gemma-4-e4b \
  --task "Search GitHub for CopeNet" \
  --start-url https://github.com \
  --max-steps 12
```

### Scripted demo still works
```bash
uv run copenet-browser-demo \
  --task "Open GitHub and search for CopeNet" \
  --start-url https://github.com \
  --max-steps 8 \
  --scripted-demo github-search
```

## Trace format

Browser-agent traces are written under:

```text
~/.copenet/logs/runs/browser-agent/
```

Each step row records:
- timestamp
- task_id / session_id
- step_index
- task
- url_before
- page_title
- observed_elements_count
- selected_action
- action_args
- validation_result
- execution_result
- page_change
- url_after
- screenshot_path
- error
- stop_reason

## Phase 3 behavior notes

### Ranking improvements
Higher priority:
- visible search inputs
- inputs with placeholders / aria labels
- meaningful nav/search controls
- elements near the top viewport

Lower priority:
- skip links
- empty links
- footer junk
- language selectors
- boilerplate crumbs

### Finish gate
The loop rejects `finish` unless visible page evidence supports the task.
For the GitHub CopeNet demo, `CopeNet` must be visible in the page state and the finish summary must reference that evidence.

### Provider repair path
If the provider returns invalid JSON:
1. parse failure is captured
2. a repair prompt is sent once
3. the repaired JSON is parsed again
4. hard failure only happens if the repaired output is still invalid

## Known limitations

- observer still relies on text-centric DOM compression, not visual grounding
- stable ids are re-assigned per observation pass
- provider-backed behavior is only as good as the model’s JSON obedience
- there is no replay viewer yet, only JSONL traces
- auth / login / captcha flows are intentionally not handled beyond safe stop/ask-user behavior
- search success confirmation is currently keyword/evidence based, not semantic result understanding

## Next Phase 4

- screenshots / vision fallback when DOM compression is weak
- auth-safe browser sessions
- replay viewer for browser traces
- deeper CopeNet tool/runtime integration
- stronger page-success heuristics and result extraction
- persistent browser sessions tied into CopeNet operator workflows

## Why this lives in CopeNet first

CopeNet already has the right instincts:
- traces
- structured runtime surfaces
- orchestration mindset
- portability pressure

So the prototype belongs here first. Once the loop is real, we can port the pattern into the broader OpenClaw/CopeNet integration cleanly.
