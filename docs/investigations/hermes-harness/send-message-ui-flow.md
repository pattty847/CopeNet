# send_message UI Flow — CopeNet Design Spec

## Summary

This document defines the operator-facing UX for `send_message` — CopeNet's first outbound communication primitive. It covers how operators see configured destinations, how a message moves from draft to sent, and how each state surfaces in the UI.

---

## Background

Hermes's `send_message` tool (`tools/send_message_tool.py:112`) is a strong reference for the tool contract:
- One tool, two actions: `list` (discover destinations) and `send` (deliver)
- The tool description teaches the model when to `list` first vs. send directly
- The backend resolves friendly names to concrete addresses before sending
- Telegram is the first backend, but the public tool contract is platform-generic

CopeNet's V1 implementation should copy the *shape*, not the whole gateway stack. Start with Telegram only; keep the tool contract stable enough that adding Slack or Discord later requires only a new adapter, not a schema change.

---

## Tool Contract (model-facing)

### `send_message`

```
action: 'list' | 'send'
target?: string              # e.g. "telegram", "telegram:@copenet_ops", "telegram:12345:67890"
message?: string             # required for action='send'
```

Tool description (key behavioral guidance the model must internalize):
- When the user asks to "send to X" and X is ambiguous, call `action='list'` first.
- When the user clearly asked for a configured destination (e.g. "send to my Telegram"), call `action='send'` directly.
- Do not claim a message was sent unless the tool result confirms delivery.
- `action='list'` returns the configured destinations and their display names.
- Destinations that are not in the configured list should not be invented.

---

## Operator UX — Destination Discovery

### Where operators see configured destinations

Configured messaging destinations should be visible in the Runtime tab (right panel) as a read-only section, or in a future Settings surface. V1 minimum: the operator can see what destinations are configured without opening a shell.

Suggested placement: a "Messaging" subsection under "Runtime Info" in the Inspector panel, listing:
- Platform: `telegram`
- Target: `@copenet_ops` (or `12345`)
- Status: `configured` / `not configured`

This tells the operator whether the agent has anywhere it can send before a run starts.

### What the model sees from `action='list'`

```json
{
  "destinations": [
    { "target": "telegram:@copenet_ops", "displayName": "@copenet_ops", "platform": "telegram" }
  ]
}
```

The model resolves the friendly name and uses the concrete target in the subsequent `action='send'` call.

---

## Message State Machine

```
drafted → pending_approval → approved → sent
                           → rejected  (message not sent)
          (no approval required)
drafted ─────────────────────────────→ sent
                                     → failed
```

States:
- `drafted` — agent has composed the message but hasn't called send yet (or send requires approval)
- `pending_approval` — approval required; run is paused waiting for operator decision
- `approved` — operator approved; backend is executing the send
- `sent` — delivery confirmed by the platform adapter
- `failed` — delivery attempted but the adapter returned an error

---

## UI Flow

### Step 1: Agent drafts a message

Agent calls `send_message(action='send', target='telegram:@copenet_ops', message='...')`.

If the tool requires approval:
- Approval request artifact is emitted (see `approval-lifecycle.md`)
- `outbound_message` artifact appears in Artifacts tab with status `pending_approval`
- Paused-run banner appears in ChatWorkspace

If the tool does not require approval (future: after "always approve for this session" is set):
- Send proceeds immediately
- `outbound_message` artifact appears with status `sent` once confirmed

### Step 2: Operator reviews (if approval required)

Operator opens the Inspector panel (or clicks the paused-run banner).

The **Runtime tab** shows the `ApprovalRequestCard`:
- Tool: `send_message`
- Action class: External Communication
- Target: `telegram:@copenet_ops`
- Message body (expandable)
- Rationale: why the agent wants to send now
- Buttons: Approve / Reject / Modify

The **Artifacts tab** shows an `outbound_message` card alongside the `approval_request` card. The `outbound_message` card at this point shows status `pending_approval` and includes a link "View approval request."

### Step 3: Operator decides

**Approve:** Message sends. `outbound_message` artifact updates to `sent`. A sent-at timestamp appears.

**Reject:** Message is not sent. `outbound_message` artifact updates status to show "not sent — rejected." The `approval_request` card shows "Rejected." The run resumes with a rejection signal.

**Modify:** Operator edits the message text inline in the approval card. On submit, the modified message is sent. `outbound_message` artifact shows the modified text and status `sent`.

### Step 4: Run resumes

Paused-run banner disappears. Activity timeline shows the resolved send_message call with ok/error status. The run continues to the next step.

---

## Artifact Cards

### `outbound_message` Artifact Card

Shown in the Artifacts tab for every send attempt (successful or failed).

**Fields visible to operator:**
- Destination: platform icon + friendly name (e.g. `telegram · @copenet_ops`)
- Status badge: `Sent` / `Pending Approval` / `Failed` / `Approved`
- Message body (truncated with expand)
- Sent-at timestamp (if sent)
- Approval link (if approval was required)
- Failure reason (if failed)

### `approval_request` Artifact Card

See `approval-lifecycle.md` for full spec. In the context of `send_message`:
- Always appears before the `outbound_message` card if approval was required
- Links are bidirectional: approval card → outbound card, outbound card → approval card

---

## Failed Send Visibility

If the Telegram adapter returns an error (bad token, unreachable API, rate limit):
- `outbound_message` artifact shows status `failed`
- Failure reason is surfaced inline: "Telegram API returned 429 Too Many Requests"
- The agent receives the failure as a tool error result and can handle it (retry guidance, inform the user, etc.)

The operator should never have to check a log to understand why a send failed — the artifact card is the canonical failure record.

---

## Destination Picker (future)

V1: operator cannot change the destination from the UI — they can only approve/reject/modify the message text.

V2 consideration: allow the operator to swap the destination during the modify flow. The `modifiedPayload` shape already supports this (it can override any field of the original payload, including `target`).

---

## Required Backend Fields

See `runtime-artifact-shapes.md` for the full `OutboundMessageRecord` shape. Key fields for this flow:

```typescript
{
  messageId: string;
  platform: string;             // 'telegram'
  target: string;               // 'telegram:@copenet_ops'
  targetDisplayName: string | null; // '@copenet_ops'
  messageText: string;          // Original or modified text
  status: OutboundMessageStatus;
  approvalId: string | null;    // Links to the associated approval if one was required
  sentAt: string | null;        // Confirmed delivery timestamp
  failureReason: string | null;
}
```

---

## Open Questions

1. **Telegram thread/topic support:** Hermes's Telegram config supports topic threads (`telegram:<chat_id>:<thread_id>`). Should CopeNet's V1 address format include thread IDs? Recommend: yes, include in the target string format but not required for V1.
2. **Media attachments:** The agent may eventually want to send images or files alongside text. Defer to V2; the tool contract is forward-compatible (just add optional `media` fields).
3. **Message length limits:** Telegram has a 4096-char limit per message. The tool description should mention this so the agent doesn't draft oversized messages. Add to tool schema.
4. **Delivery receipts:** Can the Telegram adapter confirm delivery deterministically, or only that the API accepted the request? Clarify: V1 treats API 200 OK as `sent`; true delivery confirmation is out of scope.
5. **Operator notification of outbound failure:** If a send fails after the operator approved and walked away, how does the operator find out? Current answer: they'd have to check the Artifacts panel. V2: push a notification back to the operator.

---

## Assumptions

- Telegram is the only configured backend for V1. The tool contract is generic.
- `send_message` requires approval for `external_communication` class actions by default. This default can be relaxed per-session in future.
- Message text is UTF-8 plain text for V1. Markdown formatting handled by the Telegram bot API's default `parse_mode`.
- The agent always calls `action='list'` before `action='send'` when the target is ambiguous. The tool description enforces this.
- Configured destinations are set by the operator at startup (bot token + default chat id). Runtime destination switching by the agent is not supported in V1.
