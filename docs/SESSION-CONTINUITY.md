# CopeNet Session Continuity

This page defines the continuity rules that matter most for product correctness.

## Core Model

A CopeNet session is not just a UI tab. It is a durable conversation identity with:

- `sessionKey`
- locked provider binding
- locked model binding
- locked profile binding
- locked task-mode binding
- append-only transcript history
- optional provider session continuity metadata

## What Locks And When

Before first send:

- provider is editable
- model is editable
- profile is editable
- task mode is editable
- title is editable

After first send:

- provider is locked
- model is locked
- profile is locked
- task mode is locked
- title remains editable
- archived state remains editable

This is a product invariant, not just a UI preference.

## Provider Session Id

Some providers may emit a provider-native session/thread id. CopeNet stores that as `providerSessionId`.

Important behavior:

- if a provider emits a new session id, CopeNet updates stored session metadata
- if a provider never emits one, CopeNet still maintains continuity at the CopeNet session layer
- provider session id is helpful, but not the sole source of continuity truth

## Continuity Failure Philosophy

Silent continuity fallback should be treated as unsafe.

Preferred rule:

- if continuity cannot be preserved, surface it clearly
- do not silently pretend an existing conversation resumed when it actually restarted fresh

This matters most for:

- resumed CLI-backed threads
- provider-side session expiry
- broken or missing provider-native session ids

## Allowed Session Mutations

Allowed after lock:

- rename session title
- archive / unarchive
- provider session id update when emitted by the provider
- run lifecycle metadata updates

Not allowed after lock:

- changing provider in place
- changing model in place
- changing profile in place
- changing task mode in place
- rewriting old transcript messages

## Draft Session Semantics

Draft sessions exist so users can stage a conversation before committing to it.

Required behavior:

- a draft may be configured before first send
- first successful send commits the binding
- later switching runtime/model should become a new chat or future branch flow, not an in-place mutation

## Failure Cases To Handle Carefully

### Provider session id missing

Not automatically a bug. Some providers do not support continuity the same way. CopeNet should still preserve the session identity at its own layer.

### Provider resume fails

Do not silently start a fresh context while pretending it is the same conversation. Surface the failure.

### Model catalog changes

Previously locked sessions should remain intelligible even if a model disappears from current discovery output. Missing current availability is not permission to mutate historical session metadata.

### Concurrent sends

One in-flight run per session is allowed. A second send against the same session should be blocked, rejected, or explicitly routed through the existing in-flight semantics.

## What Future Work Must Preserve

Any future branching, resume, Sentinel integration, or multi-agent handoff work should preserve:

- session identity clarity
- explicit continuity state
- append-only history
- no silent fallback-to-fresh-session behavior

That is the difference between “chat app glue” and a real orchestration substrate.
