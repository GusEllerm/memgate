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

## Memory types (deferred)

The taxonomy will largely be adopted from whichever memory system is chosen. "Selective" environments need at least one distinction, such as opinion versus fact, to gate on.

## Open for discussion

- [ ] **Group memory.** Should an environment be able to switch a location to "only the same group recalls it together", like a shared in-joke? The default is any participant.
- [ ] **Retelling.** A carries an opinion out of L and tells it to D in M. D's memory is tagged {loc:M, with:A, with:D}. That is how ideas spread, and it is fine for open environments. Is it also the intended behaviour for selective ones?
- [ ] **Forgetting over time.** Should memory also fade (decay, capacity limits)? That is another lever for selectivity.
- [ ] **Threat model.** Is enforcement about keeping the simulation accurate (agents cooperate), or must it hold against agents trying to leak? This decides how much side-channel hardening is needed.
- [ ] **Evolution and training.** If agents evolve by training on their experiences, a *Severance* environment must also be kept out of the training data. Memory filtering alone would not make them forget.
