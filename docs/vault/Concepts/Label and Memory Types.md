---
type: design
status: draft
authority: describes
summary: "Selective memory for a social simulation of agents: three label types (identity, location, participants); participants recall a discussion in its location; personal memory is always readable, and the environment decides what may enter it."
created: 2026-09-25
updated: 2026-09-25
tags: [agentic-memory, design, permissions, memory-types]
---

# Label and Memory Types

*Draft 2026-09-25. Rulings are in [[Decision Log]]; the rest is Claude's proposal. Extends [[Label Rule Table]]. The host system is described in [[Context-Scoped Memory Permissions]].*

**The idea.** Labels mostly exist to give agents **selective memory**, not to secure data. What an agent can recall depends on where it was and who it was with. So agents who lived through different things form different opinions. Environments set the strictness, from "keep what you learned" to *Severance*.

## Label types (accepted: start with three)

| Type | Example | Granted when | Within the type |
| --- | --- | --- | --- |
| Identity | self:A | Agent A is acting | Only the owner |
| Location | loc:L | The agent is in conceptual location L | Required |
| Participants | with:A, with:B, with:C | The agent is one of them | Any one suffices (direction accepted, under discussion) |

Across types, every type on an item must be satisfied. Within the participant type, holding any one of the labels is enough. Label-set IDs handle this without trouble, because the policy checks each stored label set and the store only sees IDs.

**Derived memories and participants (proposed, 2026-09-25).** A derived memory must be readable only by an agent who could read every one of its sources. For identity and location, where every label must be held, that means taking the union of the sources' labels. For participants, where one's own label suffices, the union would be wrong: a summary of two discussions, one with {A, B} and one with {C}, tagged with {A, B, C} would let C read what A and B said. The participant set must be the **intersection**, here empty. Such a memory is readable through participants by no one, unless the environment relaxes it, for example into a participant's personal memory. See [[Decision Log]].

**Example (Gus).** A, B and C discuss in L. The derived memory is tagged {loc:L, with:A, with:B, with:C}. Later, A alone in L can recall it. D in L cannot, because D wasn't there. A in another location cannot either, unless L let A carry it into personal memory.

## The environment decides (accepted)

Environments contain conceptual locations and own their rules:
- **Relaxation:** whether a derived memory may drop the location or participant labels.
- **The personal-memory gate:** whether an agent may write what it learned in L into its personal memory. That strips L's labels and makes it readable everywhere.

| Environment strictness | Personal-memory writes | Effect |
| --- | --- | --- |
| Open | Allowed | Agents carry learnings and opinions out of L |
| Selective | Allowed for some memory types (e.g. opinions, not facts) | Agents keep a stance but not the specifics |
| Severance | Forbidden | Agents recall L only inside L; outside, they have forgotten it |

## Personal memory (accepted)

- Labelled with the owner's identity label only, so the owner can always read it.
- It is how an agent's action space and opinions grow.
- It is also the only path by which a location's content leaves the location. That is why the environment gates the write.

## Retelling and provenance (accepted)

- **Retelling.** If L lets A carry an idea out, the idea may then spread: A tells D in M, and D's memory is tagged {loc:M, with:A, with:D}. By allowing the carry-out, L has accepted that its information diverges beyond L. Gus is leaning this way, not certain.
- **Provenance.** Every memory records where its ideas came from, as a trail of source memories, and the agents and locations they passed through. Provenance is lineage, not a label, and never gates access.
- **How provenance crosses agents.** When D's memory is derived from what A said, it cites the memories A recalled for that turn. Falda's recall traces already record which items were recalled and used ([[Falda]]).
- **What provenance reveals.** A trail back to L shows that L was the source, though not L's content. That is the "existence visible" option from the hidden-by-default ruling, used deliberately. In strict environments nothing leaves, so no trail points out.

## High-assurance locations

Agents are cooperative. High-assurance locations still need assurance **by design**, and the concern is **outbound** (accepted): nothing formed in L may be recalled outside L. Bringing personal memory into L is fine. Stopping messages from leaving L is a different part of the project.

Inbound needs no special rule. Memories from other locations are already locked in L by their location labels, so personal memory is the only outside information an agent brings in.

What outbound assurance takes:
- **No relaxation of L's labels.** Derived memories always keep loc:L.
- **The personal-memory gate is closed**, *Severance*-style. Agents may keep personal notes tagged {self:A, loc:L}, readable only in L.
- **No side effects on outside items.** Recalling a personal memory inside L must not update anything stored outside L: usage counts, recency boosts, reinforcement or merges. Falda's ranking uses recency and usage, and even a changed count tells the outside something about L. Recall traces made in L stay in L.
- **Beware location hierarchies.** If locations nest and a child location grants its parent's label, a high-assurance location can become readable from a neighbour. The OPA survey's exhaustive test caught exactly this: a vault became readable from the lobby ([[OPA and Rego]]). A high-assurance label must never be granted through a hierarchy, and the seal should be proven ([[Cedar]]) or at least tested exhaustively.
- **A partition per high-assurance location (accepted).** Ordinary locations and personal memory share one store, and labels decide every permission. Each high-assurance location gets its own partition (a Falda pool file, Qdrant shard key or Postgres partition), so L's items never enter the ranking statistics or caches outside searches use. Start with a single store; design the API with a partition key so this can be switched on later.

| Agent is in | Searches | Label filter |
| --- | --- | --- |
| Ordinary location M | Shared store | self:A, loc:M, any of its participant labels |
| High-assurance location L | L's partition + shared store (personal items only, read-only, no side effects) | self:A, loc:L, participants; personal items in the shared store |

Recalling a memory from ordinary location M somewhere else needs no data to move. M's environment either allowed the label to be dropped (the item becomes personal, or loses loc:M) or it didn't. Only the labels change.

## Memory types (deferred)

The taxonomy will largely be adopted from whichever memory system is chosen. "Selective" environments need at least one distinction, such as opinion versus fact, to gate on.

## Open for discussion

- [ ] **Group memory.** Should an environment be able to switch a location to "only the same group recalls it together", like a shared in-joke? The default is any participant.
- [x] Retelling: allowed when L permits the carry-out; provenance required (above).
- [x] Forgetting over time: deferred; probably the memory system's job.
- [x] Threat model: cooperative agents, assurance by design for high-assurance locations (above).
- [x] Training: not planned; labels and provenance must survive export so training data can be filtered later.
- [x] Personal memory in high-assurance locations: may be recalled inside; the guarantee is outbound only.
- [x] Isolation: one shared store; a partition per high-assurance location, switched on later via a partition key in the API.
