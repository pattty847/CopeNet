# MAO v0.1 Repo-Local Cage

MAO v0.1 is a small local workflow for safe multi-agent work:

- one foreman
- one worker
- one task
- one git worktree
- one manifest
- one default-deny scope hook
- one test run
- one reviewed merge

Runtime state lives in `.agents/runs/` and `.agents/worktrees/`. The tracked pieces are the scripts, hooks, and this workflow note.

## Command Flow

Create a run and worktree:

```bash
python .agents/scripts/mao_create_run.py \
  --run-id v0-pilot-01 \
  --task-id T-01 \
  --objective "Add GET /api/v1/agents/ping with one test." \
  --agent codex \
  --branch agent/codex/T-01-agents-ping \
  --worktree .agents/worktrees/T-01-agents-ping \
  --allow src/copenet/host/api.py \
  --allow src/copenet/host/agents_api.py \
  --allow tests/integration/test_app_api_agents.py \
  --test "uv run --extra dev pytest -q tests/integration/test_app_api_agents.py"
```

Install hooks into the worker worktree:

```bash
python .agents/scripts/mao_install_hooks.py --worktree .agents/worktrees/T-01-agents-ping
```

Worker commits must modify only the manifest `allowed_paths`, and commit messages must start with the task id prefix, for example:

```bash
git commit -m "[T-01] add agents ping endpoint"
```

If a staged file escapes scope, the hook rejects the commit with `BACK TO THE CAGE: BONK`. The first violation records a retry. The second marks the manifest blocked and writes an escalation report.
