# CopeNet Session Continuity

This page defines the continuity rules that matter most for product correctness.

## Core Model

A CopeNet session is a durable conversation container with:

- a stable `sessionKey`;
- a locked provider, profile, persona, and workspace after first send;
- an operator-changeable model within the same provider;
- an operator-changeable Access level (`taskPromptId`);
- append-only transcript history;
- per-run provider/model stamps;
- optional provider-native session continuity metadata.

The model cannot change its own runtime or Access. Mid-session changes come from an
explicit operator request and affect future runs only; historical run metadata and
transcript entries never change.

## What Locks And When

Before first send, the draft may change provider, model, profile, persona, workspace,
Access, and title.

After first send:

- provider, profile, persona, and workspace remain locked;
- model may change only within the locked provider;
- Access may change;
- title and archived state may change.

Cross-provider switching is not implemented. It requires an explicit continuity design
because some providers retain server-side session state while others rely on transcript
replay.

## Provider Session Id

Some providers emit a provider-native session or thread id. CopeNet stores it as
`providerSessionId`.

- If a provider emits a new id, CopeNet updates session metadata through `SessionStore`.
- If a provider never emits one, CopeNet still maintains continuity through its durable
  transcript.
- A provider session id is useful metadata, not the sole source of truth.

If provider-native resume fails, CopeNet must not silently pretend that a fresh provider
conversation resumed the old context.

## Allowed Session Mutations

Allowed after first send:

- rename or archive/unarchive the session;
- change model within the existing provider;
- change Access;
- update provider-session and run-lifecycle metadata.

Not allowed after first send:

- change provider, profile, persona, or workspace in place;
- rewrite or delete stored transcript entries;
- let a model alter runtime or policy selection.

## Auditability

Every run records the provider and model it actually used. A later model or Access change
does not rewrite earlier messages or run records. Missing current catalog availability
does not make historical metadata mutable.

## Concurrency And Recovery

Only one run may be in flight for a session. Concurrent sends must use the existing
in-flight/idempotency behavior rather than starting a second execution.

On process startup, stale persisted in-flight markers are recovered because no run from
the previous process can still be executing. Storage failures must fail loudly; a corrupt
session index must never be treated as an empty index and overwritten.

## Future Work Must Preserve

Branching, cross-provider switching, Fleet coordination, and other handoff features must
preserve:

- clear session and lane identity;
- append-only history;
- per-run runtime provenance;
- explicit continuity failures;
- no silent fallback to a fresh context.
