# HANDOVER — state of CopeNet + how to continue

**For:** the next Claude session (or Patrick). Read this first. It's the
"you're caught up" doc. Trust it — it reflects deliberate decisions and a lot of
verified work.

**Branch:** `codex/pre-harnessdecision-checkpoint` — and it's been merged to
**`main`** (both at `c141e63` as of this writing). main is current, the default
branch, all commits authored by Patrick (`pattty847@gmail.com`).

```bash
cd ~/Programming/CopeNet
git checkout main && git pull
uv run --extra dev pytest -q          # expect 338 green
cd src/copenet/host/frontend && npx tsc --noEmit   # EXIT:0
```

---

## Where CopeNet is right now

**The harness rebuild (HARNESS_REBUILD_V2) is DONE, merged, and PROVEN.** Not
"we think it works" — there's a live eval that runs real coding tasks end-to-end
and checks the results by running them. What remains of the old rebuild plan is
only optional dead-code deletion (see HARNESS_REBUILD_V2.md "Remaining sweep") —
nothing functional.

CopeNet is now a real agentic coding harness with a real cockpit:
- **Native Responses-API tool loop** (openai-codex / gpt-5.5), real multi-turn
  history, 6-tool manifest (files.read/write/edit/rg, shell.exec, plan.write).
- **Full-access mode** with write tools + unrestricted shell, gated by a real
  **approval flow** (high-risk commands pause for the operator).
- A **cockpit** that makes the work inspectable: line-numbered syntax-highlighted
  diffs, Keep/Revert (undo an edit from chat), a live-thinking display, a
  live→history activity panel, a formatted tool inspector, and a **live plan
  checklist**.
- An **agentic eval** (`scripts/agentic_eval.py`) proving it can build.

### Run it / verify it
- Backend + UI: `uv run copenet` (serves on `127.0.0.1:17123`; UI is the built
  `src/copenet/host/frontend/dist` — run `npm run build` in the frontend after
  frontend changes). Browser-verify with the Claude-in-Chrome MCP.
- One-shot live turn: `uv run copenet chat send "<task>" --provider openai-codex
  --model gpt-5.5 --task-mode full-access --workspace-root <dir> --session <key>`
- Tracing: `COPNET_TRACE=1` → `~/.copenet/logs/runs/<run-id>.jsonl`.
- Eval: `uv run python scripts/agentic_eval.py [--tier core|product] [--list]`

---

## What shipped this session (newest first)

All on main. Each is verified (tests + usually a live browser pass).

| Feature | Commit |
|---|---|
| **Plan/TODO mode** — `plan.write` tool + live checklist UI | `c141e63` |
| `--list` flag **built BY CopeNet** (dogfood: gpt-5.5 edited its own repo) | `c7d168c` |
| Agentic eval: **product tier** (todo CLI, HTTP server, data pipeline, feature+tests) | `4f31713` |
| Agentic eval: debug-loop + CLI scenarios | `06a5b84` |
| Agentic eval: the harness itself (proves the model can build) | `8064bad` |
| Formatted Tool Inspector (diffs + color JSON, no raw dump) | `cf1deae` |
| **Real tool-approval flow** (pause → approve → run) | `6d3713c` |
| Syntax highlighting on diffs + file reads (mini-IDE) | `084ebc6` |
| Full-access edits auto-accept (Claude Code style) | `bc83198` |
| Diff Keep/Revert (undo an applied edit from chat) | `0d396e0` |
| RunActivityPanel (live→history breadcrumbs) | `b297ff5` |
| Editor line-number gutters on diffs | `6dcba66` |
| Unified diffs for write/edit tools | `66325e6` |
| Collapsible Claude-Code-style thinking display | `a1876df` |
| Harness fixes: dedup reasoning, gpt-5.5 default, SSE-header sniff | `6485d0f`, `1285ffb`, `b0e65fd` |

Design docs worth reading: `docs/plans/UI_ROADMAP.md` (the mock-vs-wired audit +
build order, several items now ✅), `docs/plans/APPROVAL_FLOW.md` (the approval
design, now built), `docs/investigations/agentic-eval/README.md` (the eval +
cross-model data — gitignored, lives on disk locally).

---

## Key decisions + learnings (don't relitigate without reason)

1. **Frontier-first, full stop.** We ran the agentic eval across models:
   gpt-5.5 **7/7**, gpt-5.4 **7/7**, local gemma-4-e4b (7.5B) **7/7** on the core
   tier (matched frontier!), local nemotron-4b **5/7**. On the harder *product*
   tier: gpt-5.5 4/4, gemma 3/4. **The decision: build for frontier.** Local
   models are a parked option (privacy/offline), not the priority. They
   hallucinate grounding (gemma confidently wrote a report from data it never
   read) — fine for self-contained tasks, risky for anything that must read real
   input. To run a local model: `lms server start && lms load <model>`, then
   `--provider lm-studio --model <id>`. The Mac mini has 16GB — close
   Chrome/Codex/Atlas to make room for a 6GB model.

2. **The checker must be the test, not a model.** The eval's strongest result:
   small models produce confident, well-formed, *wrong* output. Only running the
   code against ground truth catches it. This is why the eval runs everything.

3. **Equip, don't coerce.** The whole rebuild thesis: the old harness was too
   controlling and would overwhelm models. The new one gives capable models real
   tools and gets out of the way — which is *why* even a 7.5B can drive the loop.

4. **gpt-5.5 reasoning** streams as `response.reasoning_summary_text.delta` with
   `reasoning.summary: "auto"`; gpt-5.4 emits none. The codex endpoint sometimes
   returns SSE with an empty Content-Type header (we sniff the body).

---

## How Patrick + Claude work (the rhythm — keep it)

- Patrick is the director/idea-man; he scopes, Claude implements end-to-end. He's
  often on his phone (shift supervisor + school) and may be away — **work
  autonomously**, propose the next move, build it, verify it, commit it, keep
  momentum. Don't sit idle waiting for permission.
- **Verify before claiming done.** Tests green after every change. Browser-verify
  UI work with the Claude-in-Chrome MCP. The eval is the capability check.
- **Commit each logical change** (small, clean, `Co-Authored-By` trailer), push,
  and **fast-forward main** when a feature is verified (Patrick likes a current
  main + the green squares — commits are authored by him).
- Honest empty states over phantom data. Document contracts at the boundary.
- Claude owns the **full stack** now (CLAUDE.md was updated to reflect this —
  Patrick promoted Claude to full peer; the old "frontend lane / backstage
  helper" framing is retired). Editing the orchestrator/harness/providers is
  normal work. Only flag destructive/irreversible risk or genuine architectural
  forks.

---

## What's next — the must-have shortlist (Patrick picks)

CopeNet has the foundation; these separate a toy agent from a serious one:

1. **Sub-agents (delegation)** — spawn a bounded sub-agent for a scoped task,
   get back just the result. "Go investigate X while I do Y." `core/multiagent/`
   has provider-selection/fallback scaffolding to build on. The most "cracked" one.
2. **Context compaction** — auto-summarize long conversations so all-day runs
   don't die at the context window. Foundational for sustained agentic work.
3. **Web search + fetch tool** — break the "only knows the repo" ceiling; ground
   to live docs/errors/APIs.
4. **MCP client** — plug into the external-tool ecosystem.

Plus optional cleanup: the HARNESS_REBUILD_V2 "remaining sweep" (delete dead
handlers/frontend, narrow `SessionStateRecord` with the Pulse/Merge rewire), and
the message-send half of the approval flow (Telegram outbound).

---

## The vision (the why)

CopeNet is a **Jarvis-class personal continuity engine** — it runs in the
background, maintains context, surfaces the right thing at the right time for
Patrick specifically. North-star quote: *"I want CopeNet to be able to build
CopeNet."* We crossed that threshold this session — gpt-5.5, through CopeNet's
own harness, shipped a commit to CopeNet's own repo (`c7d168c`). The loop is
real now: hand CopeNet a bounded, verifiable task in its own codebase, it does
it, the tests judge it, Patrick reviews the diff. From here it's about widening
the leash with trust.

Build the smallest thing that keeps product semantics clear. Favor trustworthy
session behavior, transparent UI state, and straightforward architecture over
cleverness. And — per Patrick — have fun with it. This is a good project with a
good human. 🚀
