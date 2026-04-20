# Meme Lab V2: Taste Engine Over Prompt Engine

## Summary

Meme Lab v1 proved the local model API path and the stateless endpoint, but it still behaves like a polite idea generator wearing meme clothes.

Meme Lab v2 shifts the center of gravity from a single prompt to a small taste runtime:
- Sable Brain remains the canonical curated humor source
- CopeNet builds a structured runtime index from that markdown vault
- each ideation request assembles a compact retrieval pack
- a mutation planner forces domain collisions, artifact shells, and escalation pressure
- an anti-mid judge pass filters smooth or normie-safe candidates before they hit the UI

## Why V1 Misses

The current failure mode is not infrastructure or censorship. It is statistical average.

V1 still defaults toward:
- generic legibility
- broad office-humor phrasing
- polished copy instead of discovered artifacts
- too little artifact-shell pressure
- too little fake authority and domain contamination
- no explicit rejection of mid outputs

## Canonical Source And Runtime Split

Canonical source:
- `/Users/copeharder/Documents/Obsidian/Sable Brain/05 Research/Meme Style Library`

Runtime behavior:
- markdown stays canonical and human-editable
- CopeNet reads the vault directly
- CopeNet writes a generated JSON retrieval index as a runtime cache
- future feedback analytics may use a separate store later, but not in v1

## Runtime Stages

### 1. Knowledge ingestion
Normalize markdown into document types:
- voice map
- humor mechanism
- meme engine
- caption pattern
- nuance note
- feedback rule
- case study
- lexicon note
- prompt design note

### 2. Retrieval pack
Build a compact, deterministic pack per request:
- `voice_summary`
- `anti_patterns`
- `engine_pack`
- `mechanism_pack`
- `caption_pattern_pack`
- `nuance_pack`
- `case_study_pack`
- `feedback_pack`
- `lexicon_pack`
- `artifact_shell_pack`

### 3. Mutation planning
Derive:
- style mode
- 2-4 domain collision candidates
- artifact shell candidates
- escalation mode
- anti-pattern bans
- mutation notes

### 4. Generation pass
Compose a stronger prompt from:
- the meme system prompt
- retrieval-pack excerpts
- mutation notes
- artifact-shell pressure
- anti-mid bans

### 5. Judge pass
Apply one explicit anti-mid pass that scores for:
- artifact shell strength
- lexical novelty
- domain collision strength
- delayed recognition
- fake authority energy
- implied lore density
- normie contamination risk

Reject obvious mid. Rewrite promising-but-too-smooth candidates once if they are close enough to salvage.

## Schema Notes

Generic internal types:
- `KnowledgeDocument`
- `KnowledgeSection`
- `KnowledgeTag`
- `KnowledgeExcerpt`
- `KnowledgePack`

Meme-specific types:
- `MemeKnowledgePack`
- `MutationPlan`
- `JudgeScorecard`

Minimal normalized fields:
- `id`
- `doc_type`
- `title`
- `source_path`
- `tags`
- `text`
- `summary`
- `section_title`
- `last_modified`

## Public API Direction

Keep `POST /api/v1/memes/ideate` as the entrypoint.

Preserve the existing response shape and add optional metadata:
- `knowledgePackVersion`
- `judgeWarnings`
- `artifactShell`
- `mutationNotes`

Do not add persistence or DB-backed feedback storage in this phase.

## Future Extensions

Likely next steps after v2:
- store structured human meme feedback events separately
- compare multiple local models against the same taste pack
- generalize the knowledge-runtime pattern to non-meme workflows
- optionally add SQLite for feedback analytics and retrieval telemetry, not as source truth
