@AGENTS.md

## Claude-Specific Notes

`AGENTS.md` is the primary guide for this repository. This file only adds behavior guidance specific to Claude-style coding agents.

### Response Style

- Lead with the action or answer.
- Keep explanations concise unless deeper detail is needed.
- Match the file’s existing style instead of introducing a personal style.
- Prefer concrete edits over long speculative design writing.

### When To Ask Before Proceeding

Ask before:

- changing session locking rules
- changing WebSocket frame shapes in a breaking way
- introducing a new top-level subsystem
- removing public methods or stored fields with compatibility impact

Proceed without asking for:

- new prompt profiles or task modes
- documentation improvements
- isolated bug fixes with clear intent
- additive RPC or UI improvements that preserve existing behavior

### Prompt/Profile Guidance

- Keep prompt composition in `src/copenet/prompts/loader.py`.
- Treat prompt files as content, not software architecture.
- Prefer readable markdown files over meta-systems.

### Provider Guidance

- Codex, LM Studio, and Ollama should all fit the shared provider contract.
- Do not push runtime-specific policy into the orchestrator if it can stay in the provider or harness.

### Complexity Check

If the solution seems to require a new registry, plugin framework, config layer, or dependency, pause and see whether a simpler path already fits the repo.
