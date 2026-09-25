---
type: session
status: active
authority: log
summary: "First session: repo, remote and livedocs vault set up; research brief drafted and split into vault notes."
created: 2026-09-25
updated: 2026-09-25
tags: [agentic-memory, session]
---

# 2026-09-25 Project setup

**Who:** Gus with Claude (Opus 5.5).

**Gus's brief.** Research different types of agentic memory system for use in another project that needs a fine-grained permission structure over an agent's memory, where context unlocks and locks parts of that memory. Start a git repo, remote, and init livedocs.

**Done.**
- Initialised the git repo and created the private remote GusEllerm/agentic-memory.
- Scaffolded the vault with livedocs new-vault at docs/vault.
- Drafted the problem and requirements in [[Context-Scoped Memory Permissions]], the rubric in [[Evaluation Criteria]], and the candidate list in [[Architecture Survey]].
- Open questions for Gus are rows in [[Decision Log]].

**Note.** Claude first misread "livedocs" as a Claude Docs artifact and drafted the brief there; Gus corrected it and the artifact was deleted. Project content lives in this vault.

**Decisions walked through with Gus.** Context is an open-ended combination of attributes (user, session, agent or agents, environment, more later); scopes are overlapping labels; locked memory is hidden, provided per-item visibility can be added later; stack not tied. Recorded in [[Decision Log]] and folded into [[Context-Scoped Memory Permissions]] and [[Evaluation Criteria]].

Gus then accepted the survey shape (memory stores and policy engines surveyed as separate layers) and kept the repo private.

**Survey started.** Gus added Falda and Redis's memory system to the survey, chose Rob Ross's Falda fork, and deferred benchmarking. Surveyed [[Falda]], [[Redis Agent Memory]] and [[Vector Store Label Filtering]], and drafted [[Label Rule Table]]. A peer Claude session also wrote survey notes; one overwrite was reverted.

**Next.** Gus rules on the four proposed label-model rows in [[Decision Log]]. The deeper pass on the Ross fork of Falda is done: [[Falda]] now reflects commit 0690078, including the recall path and every point where a label filter would be injected.
