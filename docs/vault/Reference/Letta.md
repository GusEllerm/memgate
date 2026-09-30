---
type: reference
status: active
authority: reference
summary: "Letta today is letta-code (v0.33.1 @ d7fd0a6): memory as a git-backed Markdown filesystem the agent edits freely, with background reflection. No per-item labels, no local vector search, rewrites mix locations. The V1 server (blocks, archival tags) is archived and unsupported."
created: 2026-09-25
updated: 2026-09-25
tags: [memgate, reference, survey, letta]
---

# Letta

*Surveyed 2026-09-25 from [letta-ai/letta-code](https://github.com/letta-ai/letta-code) commit d7fd0a6c (v0.33.1), the archived V1 server (commit 56ba9c25, v0.16.8, read for history only) and [docs.letta.com](https://docs.letta.com/concepts/memfs). Facts are as of that date. Listed in [[Architecture Survey]].*

**Verdict so far.** The Letta known as MemGPT is gone. The Python server with memory blocks, archival passages and sleep-time agents is archived, and its maintainers say not to use it for comparisons. Current Letta keeps memory as a git-backed Markdown filesystem that the agent rewrites freely, with no per-item labels and no local vector search. A freely rewritten core file mixes content from many locations, so under union inheritance it soon becomes unreadable almost everywhere. Letta is a poor base. Its useful ideas are git history as lineage, and a directory per label set projected into context.

## What it is

- **Current:** letta-code, TypeScript on Bun/Node, Apache-2.0, very active. It dropped the old memory-block and sleep-time migrations in 0.27.10.
- **Storage:**
  - Locally: JSON transcripts plus a git repo of memory files per agent. Local conversation search is term matching.
  - In the cloud: vector and hybrid search are closed server features.
- **V1 (archived):** Python on Postgres with pgvector or SQLite. Blocks, archival passages, identities, groups and sleep-time agents.
- **Export:** the AgentFile (.af) format is removed. Export copies the memory git repo.

## Memory architecture

- **Always in context:** the root MEMORY.md index and the other root Markdown files ("core memory"), plus the file tree.
- **Paged in:**
  - Files in subdirectories, read on demand.
  - Conversation search over past messages.
  - Compaction summaries, which the docs say "can omit exact wording or provenance".
- **Self-editing:** the agent edits memory with ordinary file tools. Every edit is committed to git behind a pre-commit hook.
- **Reflection ("dreaming"):** a background subagent reads a transcript and edits memory in a private git worktree, then merges its commits back. It fixes stale facts in place rather than appending.

## Scoping and access

- **Current:**
  - Memory is per agent, enforced by file path: a cross-agent guard plus sandbox confinement.
  - Shared memory is a whole git repository attached read-write or read-only, and is cloud-only.
  - Frontmatter is limited to a name and description, and the hook rejects anything else, so labels can't live there without a patch.
- **V1:**
  - Blocks could be shared across agents, or overridden per conversation.
  - Archival passages had tags with any/all matching.
  - On pgvector, the tag filter ran in Python **after** the SQL limit (a code TODO says to move it into SQL).
  - Identities and groups were never access control.

## Lineage

- Git gives full history per memory file.
- Reflection commits carry trailers: the transcript reviewed and the agent IDs. But the model writes them by following its prompt, so they are advisory, not enforced.
- Nothing records which sources fed a rewritten line.
- V1 block history recorded only the actor.

## Fit with our label model

| Requirement | Fit | Why |
| --- | --- | --- |
| Label pre-filter | Missing locally | No local vector search; cloud search is closed |
| Per-item labels | Missing | Frontmatter hook rejects extra keys |
| Union inheritance | Breaks | Core files and reflection mix locations; the LLM decides where to write |
| Workable mapping | One directory per label set | For example loc-L/, placed in context only while the agent is in L, with a write gate refusing edits that bring in content from outside that set, and reflection split per label set |
| Provenance | Partial | Git history is solid, but source trailers are advisory |
| High-assurance partitions | Natural fit | A separate repo or worktree per location |
| Export fidelity | Partial | Labels survive only if stored in files or commits |

**Effort:** high. It would be a fork of letta-code or a layer over it:
- labels in a sidecar file or extended frontmatter;
- label-set directories placed into each agent's checkout;
- commit trailers that inherit labels;
- our own vector store with a label-set-ID pre-filter.

## For benchmarking later

- Benchmark letta-code or the Agent SDK, not V1. The maintainers explicitly reject V1-based comparisons.
- Local mode has no semantic recall, so comparisons need the cloud backend.
- Measure leakage through core files and reflection merges, not just retrieval.
