# Observability Run Inspector

## Product goal

Observability should explain a model run from the operator's point of view: what
CopeNet sent, which tools the model could see, which tools it called, what those
tools returned, and which reasoning signal the provider actually exposed. It
must not imply access to private chain-of-thought when a provider only returns a
summary—or no reasoning channel at all.

## Delivered surface

The Observability workspace is a run-first, master-detail inspector:

- recent durable runs across active sessions
- chronological user, reasoning, tool, and assistant events
- exact tool arguments plus retained result previews or artifacts
- debug-only model input snapshots with effective instructions, messages, tool
  manifest, harness decision, transport, and reasoning configuration
- raw per-run JSONL trace events
- provider, model, duration, status, tool count, and debug-capture provenance

The Debug capture switch applies to subsequent runs and persists in
`~/.copenet/observability.json` (or under `COPNET_DATA_DIR`). `COPNET_TRACE=1`
remains a startup-compatible fallback, but the persisted operator setting is the
canonical runtime control once it exists.

## Data flow

```text
Observability UI
  ├─ observability.settings.get/update
  └─ observability.run.get(sessionKey, runId)
       └─ Orchestrator ObservabilityFacade
            ├─ RunStore durable record
            ├─ transcript entries stamped with runId
            ├─ ArtifactStore records stamped with runId
            └─ logs/runs/<runId>.jsonl
```

Standard run records remain lightweight. Debug capture adds a
`model_input_snapshot` trace event at the harness boundary, after CopeNet has
resolved the actual provider transport. This keeps prompted-tool pretext,
Responses instructions, chat messages, and offered tool schemas aligned with
what the provider received.

## Reasoning provenance

Reasoning is normalized without flattening its source:

| Provider lane | Current evidence | Inspector label |
| --- | --- | --- |
| OpenAI Codex Responses | reasoning summary delta/item | `Reasoning summary` |
| OpenAI raw reasoning-text event, if emitted | raw reasoning text | `Raw reasoning` |
| Claude CLI | no reasoning channel in CLI stream | no reasoning section |
| LM Studio / Ollama | model- and template-dependent; pending local testing | derived from runtime event metadata |

The OpenAI probe matrix tested medium/auto, high/detailed, and tool-enabled
variants. All returned short reasoning summaries. Increasing effort and summary
detail did not materially expand them, which indicates upstream summary behavior
rather than CopeNet truncation. Raw response fixtures from probes stay under the
ignored `tmp/` tree and are never committed.

## Privacy and security

- Debug capture is off by default because prompts, history, tool schemas, and
  tool output can contain sensitive operator or repository data.
- Trace serialization recursively redacts credential-shaped keys such as
  authorization, cookies, passwords, secrets, and access/refresh/API tokens.
- Traces remain local and are not sent to an analytics service.
- Existing runs cannot be retroactively upgraded to debug captures.
- Screenshots and fixtures must use synthetic sessions and prompts.

## Next work

1. Test LM Studio and Ollama models that explicitly advertise a thinking stream.
2. Add side-by-side run comparison for prompt, tool, latency, and reasoning
   differences.
3. Add derived diagnostics (malformed tool attempts, repeated calls, policy
   blocks, tool-result utilization) without interpreting prose as control flow.
4. Add retention controls and an explicit local trace purge workflow.
5. Add exportable, sanitized run bundles for cross-provider evaluation.
