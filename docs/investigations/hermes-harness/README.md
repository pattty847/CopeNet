# Hermes Harness Investigation

This workspace is for a focused investigation into how real agent harnesses behave in practice, starting with Hermes and comparing what it does well against CopeNet's current harness behavior.

## Goal

Learn concrete, reusable harness patterns that help smaller local models:

- avoid confidently lazy answers
- choose the right tools in the right order
- continue when evidence is insufficient
- keep answers tied to proof instead of repo vibes

## Why This Exists

We already learned two important things in CopeNet:

1. protocol alignment matters
2. protocol alignment alone is not enough

Moving LM Studio / Gemma 4 onto native tool calling was the right step, but the live probes now show a new failure mode:

- repeated `files.list`
- too little `files.read`
- weak or missing grounded evidence
- acceptable tool syntax, weak tool judgment

So this investigation is about **harness quality**, not just tool-call formatting.

## Working Files

- `BOOTSTRAP_PROMPT.md`
  - prompt to restart the investigation after compaction
- `NOTES.md`
  - running notes, observations, and hypotheses
- `COMPARE.md`
  - side-by-side comparisons between CopeNet and the reference harness
- `TODO.md`
  - current investigation checklist

## Scratch Space

These paths are intentionally gitignored for temporary dumps and copied snippets:

- `scratch/`
- `raw/`

Use them for:

- copied upstream prompts
- raw command output
- JSON payload captures
- quick transcripts
- one-off comparison artifacts

## Suggested Workflow

1. clone or point Codex at the reference harness repo
2. trace its actual tool loop, provider contracts, and continuation logic
3. compare those choices against CopeNet's live failure modes
4. extract reusable patterns
5. patch CopeNet only after we can explain why the reference behavior works better
