# Telegram Settings / Messaging Configuration — CopeNet UI Design Notes

## Summary

This document describes the operator-facing settings surface for configuring CopeNet's outbound messaging. V1 is Telegram-first but designed to accommodate additional platforms. The UI is currently mocked; backend wiring is deferred until the Telegram adapter exists.

---

## Design Principles

1. **Platform-generic shell, Telegram-specific content first.** The UI structure is `Platform → Destinations → Approval Policy`. Any new platform (Slack, Discord) fits in the same shell.

2. **Operator should see the full picture without opening a shell.** The settings surface gives the operator complete visibility into: which platform is connected, what bot is active, what destinations are configured, and what the approval policy is.

3. **Read-only for now; plumbed for edit.** All edit controls (Add, Edit, Delete) are visible and have the right affordances but show "requires backend config" tooltips. When the backend ships, these unblock.

4. **Approval policy is first-class.** The toggle and per-destination overrides make the approval model explicit — it's not buried in a config file.

---

## Component: `MessagingSettingsPanel`

File: `src/copenet/host/frontend/src/components/MessagingSettingsPanel.tsx`

### Layout

```
┌──────────────────────────────────────────────┐
│ PLATFORM                                      │
│ ┌──────────────────────────────────────────┐ │
│ │ ✈ Telegram          ● Connected          │ │
│ │   @CopeNetBot                            │ │
│ │   Token: tg:7321...xxxx                  │ │
│ │   Verified: 5m ago                       │ │
│ │   [Test connection]                      │ │
│ └──────────────────────────────────────────┘ │
│   Additional platforms (Slack, Discord) …    │
│                                              │
│ ▾ DESTINATIONS · 3 configured               │
│ ┌──────────────────────────────────────────┐ │
│ │ ✈ telegram  [Default]     ⚠ Approval    │ │
│ │   @copenet_ops                           │ │
│ │   telegram:@copenet_ops                  │ │
│ │                       [✎] [📝] [🗑]     │ │
│ ├──────────────────────────────────────────┤ │
│ │ ✈ telegram                  ✓ Direct    │ │
│ │   Private Test Chat                      │ │
│ │   telegram:987654321                     │ │
│ │                       [✎] [📝] [🗑]     │ │
│ ├──────────────────────────────────────────┤ │
│ │ ✈ telegram             ⚠ Approval      │ │
│ │   Engineering Group · Alerts thread     │ │
│ │   telegram:-1001234567890:42             │ │
│ │                       [✎] [📝] [🗑]     │ │
│ └──────────────────────────────────────────┘ │
│   [+ Add destination]                         │
│   Requires backend configuration              │
│                                              │
│ APPROVAL POLICY                              │
│ ┌──────────────────────────────────────────┐ │
│ │ Require approval by default    [ON ●]    │ │
│ │ Per-destination overrides above apply.   │ │
│ └──────────────────────────────────────────┘ │
└──────────────────────────────────────────────┘
```

---

## Telegram Platform Section

### Fields

| Field | Source | Notes |
|---|---|---|
| `botUsername` | Resolved from Telegram Bot API on connect | e.g. `@CopeNetBot` |
| `tokenMasked` | Backend — never full token in frontend | e.g. `tg:7321...xxxx` |
| `connectionStatus` | `connected` / `disconnected` / `error` / `unconfigured` | Live status |
| `lastVerifiedAt` | ISO timestamp | When the backend last verified the token |
| `errorMessage` | String or null | Shown if `connectionStatus === 'error'` |

### "Test connection" UX

The "Test connection" button triggers a simulated 1.2s delay then shows "OK" or "Fail". When the backend ships, this calls a real `/api/messaging/test` endpoint. This is important for operator trust: they need a simple way to verify the bot token is still valid without deploying the agent.

### "Not configured" state

If `telegram: null` in `MessagingConfig`, the section shows a CTA button "Configure bot token" with a note that this requires backend config. This makes the unconfigured state visible without alarming the operator.

---

## Destinations

Each destination row shows:
- Platform icon + badge
- `[Default]` badge if `isDefault: true`
- `⚠ Approval` or `✓ Direct` approval-policy badge
- `displayName` (human readable)
- `threadLabel` (optional, for topic-aware targets)
- `target` string (monospace, full canonical form)
- Three action buttons: Edit (pencil), Compose (pen), Delete (trash)

The **Compose** button opens `SendMessageComposer` pre-targeted to this destination. This is the same as the compose button in `DestinationDirectory`, giving the operator a quick shortcut to test or use the destination.

The **Edit** and **Delete** buttons are visible but non-functional until backend config mutation is implemented.

---

## Approval Policy Section

### Fields

| Field | Description |
|---|---|
| `requireApprovalByDefault` | Boolean toggle. If `true`, all sends require approval unless overridden per destination. |
| `hardlineBlocklist` | Array of target strings that can never be agent-sent. Not exposed in UI yet — config-file managed. |

### Toggle behavior

The toggle state is derived from `MessagingConfig.approvalPolicy.requireApprovalByDefault`. When toggled:
- V1: local state only (no backend mutation yet)
- V2: calls a `messaging.updatePolicy(patch)` RPC

**When the default is `OFF`**, a subtle warning is shown: "Warning: direct sends bypass operator review." This friction is intentional — defaulting to "approval off" is a significant security posture change.

Per-destination `requiresApproval` overrides the global default. This allows "this one destination can send directly" while everything else still needs approval.

---

## Data Types

```typescript
interface MessagingConfig {
  telegram: TelegramBotConfig | null;
  destinations: MessageDestination[];
  approvalPolicy: MessagingApprovalPolicy;
}

interface TelegramBotConfig {
  botUsername: string | null;
  tokenMasked: string | null;
  connectionStatus: PlatformConnectionStatus;
  lastVerifiedAt: string | null;
  errorMessage: string | null;
}

interface MessagingApprovalPolicy {
  requireApprovalByDefault: boolean;
  hardlineBlocklist: string[];
}

type PlatformConnectionStatus = 'connected' | 'disconnected' | 'error' | 'unconfigured';
```

---

## Placement

`MessagingSettingsPanel` is placed in the **Runtime tab** of the Inspector, replacing the previous `DestinationDirectory` section. The Runtime tab now shows:

1. Pending `ApprovalRequestCard` (if a run is paused)
2. Run Timeline (if a run is paused)
3. Session Info
4. Runtime Info (provider/model/profile)
5. **Messaging Settings** ← replaced DestinationDirectory with this richer surface
6. Latest Tool Activity

---

## Backend Dependencies

| Feature | Required endpoint/event |
|---|---|
| Bot connection status | `MessagingConfig` served on WebSocket handshake or `GET /api/messaging/config` |
| "Test connection" | `POST /api/messaging/test` or `messaging.test()` RPC |
| Add destination | `POST /api/messaging/destinations` or `messaging.addDestination()` RPC |
| Edit destination | `PATCH /api/messaging/destinations/{id}` |
| Delete destination | `DELETE /api/messaging/destinations/{id}` |
| Update approval policy | `PATCH /api/messaging/policy` or `messaging.updatePolicy()` RPC |
| Live config refresh | `messaging:destinations` WebSocket event (already in contract checklist) |

---

## Open Questions

1. **Config file vs. runtime API:** Should destinations be managed via the CopeNet config file (bot token, chat IDs as YAML) or via a runtime API? For V1, config file is simpler. For V2, the runtime API allows operator self-service without touching config files.

2. **Thread/topic support:** The `threadLabel` field is shown but is informational only. The `target` string format `telegram:<chat_id>:<thread_id>` is the canonical form. Should the UI have a dedicated thread picker, or is the raw target string enough? Lean toward: show the label, edit the target string directly.

3. **Multiple Telegram configs:** Can CopeNet have two bots? The current `MessagingConfig.telegram` is a single `TelegramBotConfig | null`. If multi-bot is needed, this becomes `telegram: TelegramBotConfig[]`. Not needed for V1.

4. **Operator can see full token?** The frontend only shows `tokenMasked`. The backend should never serve the full token to the frontend. Config file access is the only way to see/rotate the full token.

5. **Destination validation:** Should the UI validate that a Telegram chat ID is reachable (i.e. the bot is a member of that chat) before saving? This would require a backend validation call. Deferred to V2.

6. **Hardline blocklist UI:** The `hardlineBlocklist` field is in the type but not surfaced in the UI. When the approval subsystem ships, this should be exposed as a read-only list (no UI for removal, since hardlines are structural safety guarantees).

---

*Generated: 2026-04-28.*
