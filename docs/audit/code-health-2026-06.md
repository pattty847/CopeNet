# CopeNet Code-Health Audit — 2026-06

Snapshot of file-size / organization debt as the codebase grows. Two parallel audits
(backend + frontend). Report only — nothing refactored yet. Thresholds (from AGENTS.md):
Python ~400 lines, JS/TS ~350 lines, >3 responsibilities per file → extract.

## TL;DR

- **Risk: MEDIUM.** Session semantics + storage are clean. The debt is concentrated in a
  handful of god-objects and unfinished extractions. Nothing on fire; refactor before it
  compounds.
- **Backend worst offenders:** `orchestrator/__init__.py` (god facade), `runtime.py`,
  `tool_loop.py`, `meme_ideation.py` — all ~1000+ lines.
- **Frontend worst offenders:** `wsClient.ts` (2415!), `DataToolsPage.tsx` (1106),
  `MessagingSettingsPanel.tsx` (832), `useAppStore.ts` (694), `types/backend.ts` (1046).
- **Cheapest high-value win:** a shared `lib/formatting.ts` — `timeAgo()` is duplicated in
  **8** frontend files.

## Backend — top items (worst first)

| File | ~Lines | Problem → suggested split |
|---|---|---|
| `core/meme_ideation.py` | 1120 | prompts + parsing + scoring tangled → `_prompts.py`/`_parsing.py`/`_scoring.py` |
| `core/orchestrator/runtime.py` | 1112 | run lifecycle + approvals + message-build + overlays → `run_state.py`/`run_messages.py`/`run_approvals.py` |
| `core/orchestrator/__init__.py` | 1077 | **god facade**, 80+ methods, 15+ subsystem re-exports → inject services, keep session lifecycle only |
| `core/harness/tool_loop.py` | 1045 | 3 strategies (native/responses/prompted), ~40% duplicated loop → per-strategy modules + dispatcher |
| `host/app_api.py` | 782 | memes + media + sessions + auth in one → `app_memes.py`/`app_media.py`/`app_sessions.py` |
| `providers/openai_codex.py` | 779 | transport + SSE parse + payload build → `responses_payload.py`/`sse_parsing.py` |
| `host/rpc_catalog.py` | 728 | 40+ handlers for 7 subsystems → `rpc_profile.py`/`rpc_persona.py`/`rpc_memory.py`/… |
| `core/profile/service.py` | 671 | loader + changelog + briefing + 11 DTOs → `profile_briefing.py`/`profile_changelog.py` |

Cross-cutting smells: duplicated `_read_json`/`_write_json`/`_append_jsonl` across
profile/messaging/pulse/workspace_intel (→ `core/_json_store.py`); scattered `_normalize_*`
helpers (→ `core/_normalize.py`); inconsistent `resolve_` vs `get_` vs `fetch_` naming.

## Frontend — top items (worst first)

| File | ~Lines | Problem → suggested split |
|---|---|---|
| `lib/wsClient.ts` | 2415 | transport + 50 normalizers + RPC + business logic → `wsConnection.ts`/`wsNormalizers.ts`/`wsRpc.ts` |
| `components/DataToolsPage.tsx` | 1106 | 9 inline sub-components, 44 hooks → extract DataSources/MediaImports/WebImports/Messaging panels |
| `types/backend.ts` | 1046 | 112 types, no domain split → split by domain; add a shared `ProviderRuntime` type |
| `components/MessagingSettingsPanel.tsx` | 832 | 37 hooks, CRUD+form+validation → `DestinationForm`, `RoutesEditor`, `useDestinationManager` hook |
| `workflows/meme/MemeLab.tsx` | 831 | arena/gallery/stream in one → per-view components |
| `components/agents/AgentComposer.tsx` | 798 | runtime selector + optimizer + voice + attach → extract `RuntimeSelector`, optimizer modal |
| `components/ChatWorkspace.tsx` | 805 | 44 store subs + 22 useState → extract `ChatComposer`/`ChatExportActions`/`ChatMergePrep` |
| `store/useAppStore.ts` | 694 | one store, ~all app concerns → Zustand slices by domain |
| `components/transcript/InlineToolRows.tsx` | 674 | 16 inline preview blocks → `ToolPreviewBlocks.tsx`/`ToolRowActions.tsx` |
| `components/RightPanel.tsx` | 566 | 3 tabs + tool feed + approvals → `InboxTab`/`RuntimeTab`/`ApprovalTab` |

Cross-cutting smells: **`timeAgo()` duplicated in 8 files** + `formatDuration` variants
(→ `lib/formatting.ts`); flat `components/` dir (58 files, no feature grouping); no
React.lazy code-splitting; `useAppStore` is a god object (every component subscribes).

## Recommended order (low-risk → high-value)

1. **`lib/formatting.ts`** — dedupe `timeAgo`/`formatDuration` from 8 files. Trivial, safe, immediate.
2. **Split `wsClient.ts`** — biggest single liability; transport vs normalizers vs RPC. Do before more RPCs land.
3. **`core/_json_store.py`** — dedupe the JSON-store helpers (2h, mechanical).
4. **`tool_loop.py`** per-strategy split — unblocks adding new strategies cleanly.
5. **`orchestrator/__init__.py`** facade slimming — highest coupling, do carefully with tests.
6. Page-component extractions (DataToolsPage, MessagingSettingsPanel) — as each surface gets touched.

Treat these as opportunistic: refactor a file when you're already in it for a feature, plus
1–2 deliberate "cleanup" passes for the god-objects (wsClient, orchestrator). Don't big-bang it.
