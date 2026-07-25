# Operator UX Model

This is the short canonical model for how CopeNet explains agent work to the operator.

## Session Home Workspace

Each session has a **home workspace** chosen in draft mode and locked on first send.

Rules:
- repo/file tools default to the home workspace
- reads/searches may roam outside it
- off-root activity must be visibly marked
- writes outside the home workspace are blocked in v1 unless a future approval path lands

The home workspace is a base camp, not a prison.

## Three Layers Of Tool Truth

### 1. Transcript
Purpose: compact causal breadcrumbs inside the conversation.

What belongs here:
- short tool receipts
- small expandable summaries
- enough context to explain why the agent said what it said

What does **not** belong here:
- giant raw file payloads
- full diff walls
- deep audit detail

### 2. Activity
Purpose: live operational pulse while a run is active, plus recent jump points.

What belongs here:
- current tool activity
- short recent tool steps
- inspect entrypoints
- blocked/risky policy signals

Activity is not the permanent verbose history wall.

### 3. Inspector
Purpose: verbose audit truth.

What belongs here:
- full paths and targets
- workspace root context
- inside/outside home classification
- full previews, diffs, patch plans, and grouped call detail
- policy reasoning when a tool was blocked or treated as risky

The inspector is the microscope at the end of the breadcrumb trail.

## Access Policy V1

Current policy is intentionally small and explicit.

### Allowed
- repo reads inside the home workspace
- repo reads outside the home workspace, visibly marked as roaming
- read-only shell commands that are confidently classified as safe

### Blocked
- writes outside the home workspace
- shell forms that hide effects with pipes, chaining, or redirection
- shell commands whose effect is not confidently read-only
- write-like git subcommands through `shell.exec`

## Labels The UI Should Surface

Depending on the tool result, CopeNet may surface:
- `inside home`
- `outside home`
- `read roam`
- `write blocked`
- `approval req` (future path)
- `shell risk`

These labels should stay compact in transcript/activity and become more verbose in the inspector.
