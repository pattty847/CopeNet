# Live Tool Activity & Provider Auth — CopeNet Frontend Notes

*Generated: 2026-04-30. Phase 4 frontend pass.*

---

## Summary

This document describes the frontend design for real-time tool execution visibility and provider authentication state in the CopeNet operator UI. It covers what was built, what backend events are still needed for ideal rendering, and open RPC gaps.

---

## What Was Built (Phase 4)

### 1. `LiveToolFeed` (`components/runtime/LiveToolFeed.tsx`)

Shows tool execution in real time during an active run. Renders in the Runtime tab, replacing the previous static "Latest Tool Activity" section.

**States rendered:**

| State | Trigger | Visual |
|---|---|---|
| `queued` | Frontend-only; no backend signal yet | Loader spinner, muted |
| `running` | No tool calls received yet; run is active | Pulsing dot + "Agent thinking…" |
| `success` | `toolExecution.ok === true` | Green checkmark chip |
| `blocked` | `ok === false` + summary contains "blocked"/"policy" | Amber shield chip |
| `failed` | `ok === false` (other) | Red X chip |

**How it receives data:** `wsClient.handleChatEvent` → `store.pushLiveToolCall()` → `useLiveToolCalls()` hook.

**Lifecycle:** `store.clearLiveToolCalls()` is called when `chat.send` starts a new run. `store.setLastTurnState()` captures the final turn snapshot from the `final` event.

**Also exported:**
- `InlineToolChip` — small inline chip for use in message renderers
- `TurnSummaryStrip` — post-run "N tools, M failed" summary shown in `RunActivityPanel`

---

### 2. `ProviderAuthCard` (`components/ProviderAuthCard.tsx`)

Operator-visible auth status for a provider. Currently shown in Runtime tab when `currentProvider === 'openai-codex'`.

**States rendered:**

| State | Trigger | Shows |
|---|---|---|
| Authenticated | `authenticated && !expired` | Green check, accountId, expiry time, Logout button |
| Expired | `authenticated && expired` | Orange warning, expiry, login CTA |
| Not authenticated | `!authenticated` | Red ShieldAlert, "Log in to Codex" button |
| Backend unavailable | RPC error | Error message + backend dep note |

**Login flow:** "Log in" → calls `provider.auth.beginLogin` → shows `authorizeUrl` link → operator opens in browser → callback hits `localhost:1455/auth/callback` directly → operator clicks Refresh to pick up new status.

---

### 3. New adapter hooks (`runtime/adapter.ts`)

| Hook | Returns | Backend dep |
|---|---|---|
| `useLiveToolCalls()` | `LiveToolCall[]` from store | None — derived from existing delta events |
| `useLastTurnState()` | `TurnStateSnapshot \| null` | `turnState` on final event (already in payload) |
| `useProviderAuth(providerId)` | `{status, loading, error, refresh}` | `provider.auth.status` RPC |

---

### 4. Store additions (`store/useAppStore.ts`)

```typescript
liveToolCalls: LiveToolCall[]
pushLiveToolCall(call): void
clearLiveToolCalls(): void
lastTurnState: TurnStateSnapshot | null
setLastTurnState(snapshot): void
providerAuthStatuses: Record<string, ProviderAuthStatus>
setProviderAuthStatus(id, status): void
clearProviderAuthStatus(id): void
```

---

### 5. `RunActivityPanel` improvements

- `blocked` tool calls now render with amber Shield icon instead of red X
- Post-run turn state summary (`TurnSummaryStrip`) shown at bottom when `lastTurnState` is non-null
- Open questions from `turnState.openQuestions` shown as amber annotations

---

### 6. Runtime tab reorganization

New order:
1. Pending approval card (if paused)
2. **Live tool feed** (if run active; hint if idle)
3. Session info
4. Runtime info (provider/model/profile/mode)
5. **Provider auth card** (openai-codex only, when selected)
6. Run timeline (if paused)
7. Messaging settings

---

## Backend Events Needed for Ideal Live Tool Rendering

### Gap 1: No per-tool-call real-time events

**Current behavior:** The orchestrator emits `ProviderEvent(kind="meta", metadata={toolExecution, toolResult, turnState})` per tool call, but these are **consumed internally** and not forwarded to WebSocket clients. The `toolExecution` payload only reaches the frontend when it's attached to a subsequent `delta` or `final` event.

**Effect on UI:** Tool executions appear in the feed as they complete, but only one at a time and only when the model produces text output after a tool call. If the model calls multiple tools before generating any text, the frontend won't see them until the first delta.

**What's needed:**
```json
// New WebSocket event type:
{
  "event": "tool:called",
  "payload": {
    "runId": "...",
    "sessionKey": "...",
    "toolId": "files.read",
    "callId": "...",
    "arguments": { "path": "..." }
  }
}

// Followed by:
{
  "event": "tool:result",
  "payload": {
    "runId": "...",
    "sessionKey": "...",
    "toolId": "files.read",
    "callId": "...",
    "ok": true,
    "summary": "Read 420 lines",
    "durationMs": 14
  }
}
```

With these events, the `queued` and `running` states become fully live. Without them, `running` is approximated by "run is active, no tool yet" and `queued` is not rendered.

### Gap 2: No `durationMs` in `toolSteps`

`SessionRunRecord.toolSteps` does not include `durationMs` per step. The `ActivityToolCall` type has this field but it's always populated as `0` in the frontend mapper (`mapToolStep` in adapter.ts).

**What's needed:** Backend should include `startedAt` + `completedAt` or `durationMs` in each `RunStep`.

### Gap 3: `turnState` not yet in `ChatEventPayload` type

`ChatEventPayload` in `types/backend.ts` does not declare `turnState`. The wsClient reads it via `(payload as unknown as Record<string, unknown>).turnState`. The backend does send it on `final` events.

**Fix needed:** Add `turnState?: Record<string, unknown> | null` to `ChatEventPayload` in `types/backend.ts`.

---

## Provider Auth RPC Gaps

### What exists

All four RPCs are wired in `rpc_dispatch.py` and `rpc_catalog.py`:
- `provider.auth.status` → `ProviderAuthStatus`
- `provider.auth.beginLogin` → `{loginId, authorizeUrl, redirectUri, state}`
- `provider.auth.completeLogin` → `{status}` (not needed from UI — callback is server-side)
- `provider.auth.logout` → `{status}`

### What's missing for ideal UX

1. **No WebSocket push on auth state change.** When the operator completes login in their browser, the UI doesn't know without an explicit `refresh()` call. A `provider:auth:updated` event would allow the card to update automatically.

2. **`beginLogin` returns `login` not `authorizeUrl` directly.** The wsClient wraps this — no change needed in UI.

3. **`provider.auth.status` RPC is not in `rpc_dispatch.py` mapping by that name.** Check: the dispatch uses `"provider.auth.status"` in the source. Verify that `rpc_dispatch.py` routes this correctly (it does: see line 57: `elif req.method == "provider.auth.status"`).

4. **`ProviderAuthStatus` shape from the backend.** The `status()` method in `openai_codex.py` returns:
   ```python
   {
     "provider": "openai-codex",
     "profileId": "openai-codex:default",
     "requiresAuth": True,
     "authType": "oauth",
     "authenticated": bool,
     "expired": bool,
     "accountId": str | None,
     "expiresAt": int | None,   # unix ms
     "scopes": list[str],
     "storePath": str,          # excluded in frontend type
   }
   ```
   Frontend type matches except `storePath` (intentionally omitted).

---

## UI Assumptions Made

1. **`blocked` detection is heuristic.** Tool calls where `ok === false` and `summary` contains "blocked" or "policy" are classified as `blocked`. This matches the `channel: "policy"` pattern from `tool_loop.py` but isn't surfaced explicitly in the `toolExecution` payload. Ideally the payload would include a `channel` field.

2. **`liveToolCalls` reflects "completed" tools only**, not truly in-flight ones. The current backend shape doesn't allow distinguishing "just called, not yet returned" from "about to be called." This is a known limitation until `tool:called` events ship.

3. **Provider auth card only shown for `openai-codex`.** Other providers (codex-cli, lm-studio) don't require OAuth. When additional OAuth providers are added, the condition `currentProvider === 'openai-codex'` should be driven by `provider.requiresAuth` from the providers catalog.

4. **Login URL is shown as a copyable link**, not a system browser opener. The Electron/native path for `shell.openExternal(url)` is not available in the web frontend. When CopeNet ships as a desktop app, replace the `<a>` link with an IPC call.

5. **`TurnStateSnapshot` is parsed defensively** from `(payload as any).turnState`. A proper type on `ChatEventPayload` would make this safe.

---

## Next Frontend Pass Suggestions

1. **Wire `tool:called` + `tool:result` events** once backend emits them — update `LiveToolFeed` to show `queued` → `running` → `success/failed` transitions per call
2. **Add `durationMs` to `RunStep`** and show per-call timing in `RunActivityPanel`
3. **Add `channel` field to `ToolExecution`** to replace heuristic blocked detection
4. **Add `provider:auth:updated` WebSocket event** so `ProviderAuthCard` auto-refreshes
5. **Add `turnState` to `ChatEventPayload` type** and remove the `unknown` cast in wsClient
6. **Provider health overview on Home page** — a mini card per provider showing connection + auth state at a glance (uses `useProviderAuth` hook already built)
7. **Search bar removal from Agents page** — the global search bar should only appear on the Home page; Agents view should have no top bar (⌘K palette is the access point)
