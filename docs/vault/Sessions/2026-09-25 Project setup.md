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

**Design discussion with Gus.** The host system is a social simulation that evolves agents into diverse research entities, and labels give them selective memory. Accepted: all-of label check with any-of within participants, label-set IDs, union inheritance that the environment may relax, three label types (identity, location, participants), personal memory always readable with environment-gated writes, provenance of ideas, cooperative threat model with outbound-only high assurance, one shared store with partitions for high-assurance locations. See [[Label and Memory Types]] and [[Decision Log]].

**Survey, round two.** Surveyed [[Collaborative Memory]], [[Mem0]], [[Letta]] and [[Zep and Graphiti]], then the policy engines: [[Cedar]], [[OPA and Rego]] (with Casbin and Oso) and [[OpenFGA and SpiceDB]]. An OpenFGA load of 100k label sets ran over 20 minutes; it was capped and rerun at 10k, and the bench containers were removed.

**Engine chosen.** After reviewing an interactive Cedar briefing (linked from [[Cedar]]), Gus adopted Cedar for policy. An in-process index stays as the fallback and performance baseline.

**Coverage.** Gus asked for coverage of the popular systems. [[Memory System Landscape]] ranks 37 open-source systems and 13 managed services, 17 of them verified against code. Full reviews: [[Hindsight]] (best fit so far), [[Honcho]], [[Cognee]]. While mapping Cognee, Claude found that its own Cedar sketch granted participant labels to everyone present; it was fixed. Claude also proposed that derived memories take the intersection of participant sets, not the union.

**Next.** Gus rules on hosted services and the participant-intersection rule; then shortlist and prototype with a planted-secret leak test.
