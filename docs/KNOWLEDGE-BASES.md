# Knowledge Bases

CopeNet can work with local knowledge sources without requiring any one personal setup. The public repo stays generic on purpose: you bring your own notes, markdown vaults, research folders, or curated creative libraries.

## Recommended pattern

Use a checked-in example file as the public template:

- `config/knowledge-sources.example.toml`

Keep your actual machine-specific paths in a local override that is ignored by git:

- `config/knowledge-sources.local.toml`

This gives you three benefits:

- public docs stay shareable
- private paths do not leak into the repo
- future workflow integrations still have a clear place to point

## Current runtime hooks

Today, the most concrete knowledge-base integration is the Meme Lab knowledge runtime. It can optionally read from a local markdown library through:

- `COPNET_MEME_KB_ROOT`
- `COPNET_MEME_KB_CACHE_DIR`

If `COPNET_MEME_KB_ROOT` is not set, CopeNet falls back to a generic local default under:

- `~/.copenet/knowledge/meme-style-library`

That default is intentionally generic and safe for public repos.

## Suggested local workflow

1. Copy `config/knowledge-sources.example.toml` to `config/knowledge-sources.local.toml`
2. Point the local file at your own markdown roots
3. Export any environment variables you want CopeNet to use at runtime
4. Keep the checked-in example generic so other users can adapt it

## Design intent

Knowledge-source integration in CopeNet is meant to be:

- local-first
- optional
- workflow-specific
- compatible with private personal systems

The goal is not to force one knowledge-base architecture. The goal is to make CopeNet a safe place to plug your own systems into operator workflows over time.
