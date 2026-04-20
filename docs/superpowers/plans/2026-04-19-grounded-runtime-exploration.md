# Grounded Runtime Exploration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make CopeNet push local models toward grounded repository understanding instead of shallow directory-summary answers.

**Architecture:** Tighten the prompted tool loop so repository-inspection prompts explicitly demand evidence from meaningful files and discourage stopping after listings. Extend runtime probe classification so probe artifacts can distinguish successful multi-tool continuation from actually grounded answers based on file-reading/search evidence and cited repository paths.

**Tech Stack:** Python, pytest, FastAPI-adjacent harness/orchestrator runtime, LM Studio live probes

---

### Task 1: Strengthen Probe Classification For Grounded Exploration

**Files:**
- Modify: `src/copenet/probes/runtime_bundle.py`
- Test: `tests/unit/test_runtime_probe_bundle.py`

- [ ] **Step 1: Write the failing test**

```python
def test_classify_probe_bundle_flags_listing_only_repo_answer(tmp_path: Path) -> None:
    spec = ProbeSpec(name="architecture_setup_probe", prompt="Explain architecture")

    listing_only = classify_probe_bundle(
        probe=spec,
        run_record={
            "status": "ok",
            "toolSteps": [
                {"toolId": "files.list", "status": "ok", "ok": True},
                {"toolId": "files.list", "status": "ok", "ok": True},
                {"toolId": "tool.batch", "status": "ok", "ok": True, "batched": True},
            ],
            "outputSummary": "The repo probably uses src/copenet for core logic.",
            "terminalReason": "completed",
        },
        transcript=[{"role": "assistant", "content": "The repo probably uses src/copenet for core logic."}],
        artifacts=[],
        trace_path=None,
    )

    assert listing_only["classification"] == "ungrounded_repo_answer"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --extra dev pytest -q tests/unit/test_runtime_probe_bundle.py -k ungrounded_repo_answer`
Expected: FAIL because the current classifier still returns `batch_success`

- [ ] **Step 3: Write minimal implementation**

Add a groundedness heuristic in `classify_probe_bundle()` that treats repository-inspection probes as ungrounded when:
- tools were used, but none of them were `files.read`, `files.search`, or `context.prepare`
- and the assistant answer does not cite specific file paths beyond broad top-level folders

Return a new classification string: `ungrounded_repo_answer`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --extra dev pytest -q tests/unit/test_runtime_probe_bundle.py -k ungrounded_repo_answer`
Expected: PASS

### Task 2: Tighten Tool-Loop Prompting Toward Evidence Gathering

**Files:**
- Modify: `src/copenet/core/harness/tool_loop.py`
- Test: `tests/integration/test_tool_loop.py`

- [ ] **Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_harness_follow_up_prompt_demands_grounding_before_repo_summary(tmp_path: Path) -> None:
    provider = SequencedPromptProvider(
        outputs=[
            '{"tool_id":"files.list","arguments":{"path":"."}}',
            "Grounded answer.",
        ],
    )
    harness = ChatHarness()
    tool_context = ToolExecutionContext(
        workdir=tmp_path,
        session_key=None,
        provider_name="prompted",
        model=None,
        session_store=SessionStore(path=tmp_path / "index.json"),
        transcript_store=TranscriptStore(root_dir=tmp_path / "history"),
        providers={"prompted": provider},
        policy=ToolPolicy(),
        trace=None,
    )

    async def tool_executor(request: ToolExecutionRequest, context: ToolExecutionContext) -> ToolExecutionResult:
        return ToolExecutionResult(tool_id=request.tool_id, ok=True, summary="ok", output={"entries": []})

    _, stream = await harness.run_turn(
        provider=provider,
        prompt="Use tools to explain the architecture and setup path for CopeNet.",
        provider_session_id=None,
        abort_event=asyncio.Event(),
        available_tools=ToolRegistry().list_tools(),
        tool_executor=tool_executor,
        tool_context=tool_context,
    )
    [event async for event in stream]

    assert "Before answering a repository-architecture or setup question" in provider.prompts[1]
    assert "cite the specific files you inspected" in provider.prompts[1]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --extra dev pytest -q tests/integration/test_tool_loop.py -k grounding_before_repo_summary`
Expected: FAIL because the follow-up prompt does not yet require cited file evidence.

- [ ] **Step 3: Write minimal implementation**

Update `compose_tool_attempt_prompt()` and `compose_tool_follow_up_prompt()` to explicitly instruct models that for repository architecture/setup/explanation tasks they should:
- gather evidence from meaningful files, not just listings
- prefer `files.read`, `files.search`, or `context.prepare`
- cite the specific files inspected in the answer
- keep exploring if they only have directory listings

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --extra dev pytest -q tests/integration/test_tool_loop.py -k grounding_before_repo_summary`
Expected: PASS

### Task 3: Surface Groundedness In Probe Reports

**Files:**
- Modify: `src/copenet/probes/runtime_bundle.py`
- Test: `tests/unit/test_runtime_probe_bundle.py`

- [ ] **Step 1: Write the failing test**

```python
def test_render_probe_report_lists_ungrounded_answers_as_failures() -> None:
    bundle = ProbeBundle(
        provider="lm-studio",
        model="gemma-4",
        probe_name="architecture_setup_probe",
        prompt="Explain architecture",
        session_key="alpha",
        run_id="run-1",
        started_at="2026-01-01T00:00:00+00:00",
        finished_at="2026-01-01T00:00:01+00:00",
        duration_ms=1000,
        classification="ungrounded_repo_answer",
        final_state="ok",
        tool_step_count=3,
        tool_ids=["files.list", "files.list", "tool.batch"],
    )
    summary = ProbeSummary(
        generated_at="2026-01-01T00:00:02+00:00",
        suite_dir="/tmp/probe_runs/demo",
        targets=[{"provider": "lm-studio", "model": "gemma-4"}],
        results=[bundle],
    )

    report = render_probe_report(summary)
    assert "## Failures" in report
    assert "### ungrounded_repo_answer" in report
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --extra dev pytest -q tests/unit/test_runtime_probe_bundle.py -k ungrounded_answers_as_failures`
Expected: FAIL until the new classification is rendered with the other failure groups.

- [ ] **Step 3: Write minimal implementation**

Ensure `render_probe_report()` treats `ungrounded_repo_answer` as a failure bucket and leaves recoveries unchanged.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --extra dev pytest -q tests/unit/test_runtime_probe_bundle.py -k ungrounded_answers_as_failures`
Expected: PASS

### Task 4: Verify Local Runtime Behavior End-To-End

**Files:**
- Verify only: `scripts/live_probe_matrix.py`
- Artifacts: `tmp/probe_runs/...`

- [ ] **Step 1: Run targeted automated tests**

Run: `uv run --extra dev pytest -q tests/unit/test_runtime_probe_bundle.py tests/integration/test_tool_loop.py`
Expected: PASS

- [ ] **Step 2: Run live LM Studio probe suite against the uncensored local Gemma model**

Run: `uv run python scripts/live_probe_matrix.py --providers lm-studio --lm-model gemma-4-e4b-uncensored-hauhaucs-aggressive --expect-trace`
Expected: completes successfully and emits a new suite dir under `tmp/probe_runs/`

- [ ] **Step 3: Inspect the resulting report**

Check: `tmp/probe_runs/<timestamp>/report.md`
Expected: any shallow listing-only architecture answers are now classified as `ungrounded_repo_answer`; grounded runs remain successes.
