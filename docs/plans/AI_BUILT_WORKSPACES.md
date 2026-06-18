# AI-Built Workspaces — design sketch

**Status:** north-star concept, not yet scoped to phases. Captured while the vision is vivid.
**Director:** Patrick · **Scribe:** Claude

## The vision (Patrick's words)

> Someone who doesn't know how to use Claude Code can just tell their agent to build them
> something. It gets a schematic we provide the model, and it knows where to put it, where
> to build it, the data sources it can use, and where to place those.

"Think of something → watch it get built in front of your face."

## The key insight: a workspace is a file the model writes

Everything we've built this week is the substrate for this, and they're all the same shape:

| Primitive | What it is | Who maintains it |
|---|---|---|
| Persona | identity files (SOUL.md, USER.md…) | model + operator (inline editor) |
| Memory | scoped markdown facts | model proposes → operator approves |
| **Workspace** | **a declarative manifest** | **model drafts → operator approves** |

So "AI builds you a workspace" is not a new kind of magic. It's: **the model writes a
workspace manifest file, and the runtime materializes it.** We already have the model
writing/maintaining declarative files (personas, memory) and a runtime that renders them.
A workspace is just the next file type — the one that composes all the others.

## What a workspace manifest declares

A single human-readable file (markdown + frontmatter, or YAML — same "readable first" rule):

- **identity** — which persona / privacy tier
- **tools** — which tool ids are enabled + their policy (task mode)
- **data sources** — which feeds/knowledge bases/files, and *where they mount*
- **layout** — which panels/sections show, in what arrangement
- **starter prompts / task modes** — domain-tuned defaults
- **seed memory** — facts the workspace starts knowing
- **domain** — e.g. `osint`, `cybersecurity`, `research`

## The "schematic" we hand the model

This is the part Patrick described — "where to put it, where to build it." It's a
**blueprint vocabulary**: a schema + worked examples that tell the model exactly what slots
a workspace has, what tools/sources are available to fill them, and the placement rules.
Concretely: a JSON Schema for the manifest + a curated system prompt + 2-3 reference
manifests. The model can only assemble from the real, registered inventory — it can't
invent a tool that doesn't exist (same discipline as the tool manifest today).

## The build flow (reuses everything we have)

1. **Intent** — "Build me an OSINT workspace for tracking a person across public sources."
2. **Draft** — model reads the blueprint + the live inventory (tool registry, data sources,
   personas) and writes a workspace manifest.
3. **Preview / edit** — the manifest opens in **the FileEditor we just built**. Operator
   reads it, tweaks it, approves it. (Honest, inspectable — not spooky.)
4. **Instantiate** — runtime materializes the manifest: provisions the persona, enables the
   tools at the right policy, mounts the data sources, lays out the panels, seeds memory.
5. **Live** — the workspace exists. The user never touched a config file unless they wanted to.

Nothing here is exotic. It's draft → approve → render, over a declarative file, against a
real inventory. The same loop as personas and memory, one level up.

## Domain libraries — where Patrick's degree becomes the moat

The blueprint is only as good as the expert knowledge encoded in it. That's the asset:
**curated, expert-authored workspace templates per domain.** What tools, sources, and
workflows actually belong in a threat-intel workspace vs. an OSINT-recon workspace vs. a
malware-triage workspace — that's domain expertise, not generic AI.

- **First domains: OSINT + Cybersecurity.** Patrick has the cybersecurity background to seed
  these well. The "boring degree" is the seed library of expert blueprints the model builds from.
- A good template library makes AI-built workspaces *trustworthy* — the model assembles from
  proven schematics instead of guessing.

## Where it slots in the build order

It composes the other arcs, so it comes after them:

1. Editor keystone ✅ (done — also the manifest preview/edit surface)
2. Personas (root + project scopes) — workspaces select/compose personas
3. Memory (scoped, draft→approve) — workspaces seed memory; same approve loop
4. **Workspace manifest schema + instantiation runtime**
5. **AI-built workspaces** — model drafts the manifest from the blueprint
6. **Domain libraries** (OSINT, cybersecurity) — expert-seeded templates

Prereqs first, payoff last. Each step is independently useful, and the last one ties the
whole thing into the "everything app."
