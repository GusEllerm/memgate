---
type: concept
status: active
authority: proposes
summary: "Trust-boundary review of memgate (2026-09-30). The read path is proved and tested and trusts only the recall context: agent and location. The write path trusts more of its caller: participants, a carry-out's source and memory type, and a note's location. It is checked in Python, not proved. Verified identity and host-attested context are deferred to the Ranch integration, with a contract recorded here. Two memory-service hardenings are accepted (2026-09-30) and due before handover; memory type stays the agent's own claim, audited. Leakage through agents' own actions (files, tools, working context, messages) is outside what a memory service can prevent; what the Ranch host must do, and what memgate can offer, is set out here."
created: 2026-09-30
updated: 2026-09-30
tags: [concept, memgate, security, trust-boundaries, knowledge-ranch]
---

# Trust Boundaries

> [!abstract] Role
> What memgate assumes about each input, who supplies it, and what has to be true elsewhere for its guarantees to hold. Written after the adversarial run was dropped ([[Review memgate adoption checks 2026-09-29]]), to narrow that gap by review and proof rather than by attack. Complements [[memgate Proofs]] (policy layer) and [[Permission Layer]] (design).

## The boundary in one picture

- **Trusted:**
  - the Ranch host, which runs the simulation and knows who is where with whom;
  - memgate: `HindsightMemory` and `AsyncHindsightMemory` in `memgate/src/memgate/adapters/hindsight/client.py`, plus the Cedar policies;
  - the gated Hindsight server with `MemgateValidator`;
  - the world file and the label-set registry.
- **Untrusted:** each agent's words. That means its queries and the text it asks to remember, and, if the agents' tools allow it, anything an agent does outside the memory service.
- **Outside the boundary, trusted by necessity:** the LLM provider. Extraction, consolidation and answering prompts go to the ALCF endpoints, which see memory content in the clear.

memgate's guarantee is only as strong as the most trusted input an agent can influence.

## Inputs to memgate

| Input | Where it's used | Who supplies it today | What memgate checks | Status |
| --- | --- | --- | --- | --- |
| The shared secret | Every call to Hindsight (`HEADER_SECRET`) | memgate's client, held in-process | The validator refuses any call without it | **Sound if agents can't reach the process.** An agent whose tools run code in the same process could read it. Run memgate as its own service. The server side must be started by `memgate serve`: Hindsight otherwise applies a `.env` found above its working directory over memgate's settings, which could drop the validator (closed in 0.3.2). The server must also prove who it is before receiving the secret. Over a loopback port, a process that binds it first would get it, so 0.4.0 adds a Unix-socket transport whose private directory is checked before every request. Requests never go through a proxy. |
| Agent identity | recall, remember, keep_note, carry_out | The caller | Must be in the world: every decision about an unknown agent is refused (`Policy._known`, since 2026-09-30) | **Trusted input.** Must come from the host, never from the agent. |
| Location | recall (what is readable), writes (what is labelled) | The caller | Must be in the world: every decision at an unknown location is refused, so a location missing from the world file can never bypass the write seal | **Trusted input.** The most important one: every read decision turns on it. Must come from the host. |
| Participants | remember (the `with:` labels) | The caller | Writer must be among them (validator) | **Trusted input.** Who was present decides who can read later. Must come from the host. |
| Query text | recall | The agent | Nothing needed | **Safe.** Filtering is by label set, not by content. Proofs R1–R6 and 0 leaks across ~11,000 probes. |
| Memory text | remember, keep_note, carry_out | The agent | Labelled by context, not by content | **Safe for what memgate controls.** Text is stored under the context's labels, whatever it says. See "Agents' own actions" for what an agent already knows. |
| Carry-out source (`source`) | carry_out: which label set the content came from | The caller | Cedar decides on the source as given, and (since 2026-09-30) only where the source is readable from the carrier's current location (C4) | **Narrowed; rest deferred.** A carry-out can no longer claim a source the carrier couldn't read where it stands. Whether the content really came from `source` is checked only once context is verified (deferred to Ranch integration). |
| Carry-out memory type | carry_out: fact, opinion, skill, episode | The caller (the agent's own classification) | Must be one the source environments let out (C2); recorded in the audit log | **Accepted as a claim** (Gus, 2026-09-30): trusted under the cooperative threat model, audited, revisited at Ranch integration. Selective environments rely on it. |
| Note location | keep_note | The caller | Validator: a label set with a location may only be written in that location | **Trusted input,** as location above. |
| Writes made inside a high-assurance location | Any write | The caller | Cedar write seal (since 2026-09-30): anything written in a high-assurance location must carry its label (W4), checked by memgate's client and again by the validator | **Closed.** Personal memory can't be written inside a high-assurance location, whatever the caller claims about a source. Proved (W1–W6) and tested live. |
| Consolidation | Hindsight's background merging | Hindsight | Observations scoped to one label set (`all_strict`); lineage audit | **Verified.** 0 violations across 9 banks, including 1,840 merged observations ([[Review memgate adoption checks 2026-09-29]]). |
| Other Hindsight operations | reflect, mental models, listing, entities, documents, chunks, files, export | The caller | Validator refuses all but stats and operation status for agents. The chunk and file routes outside a bank path still go through the bank-read check | **Verified by review.** Reflect and mental models are disabled because their tag scope can't be enforced. |

## What this means

**The read path is in good shape.** It is proved (R1–R7), tested (S1–S5, the answer-level leak check), and depends only on the recall context: agent and location. Get those from the host and recall is sound.

**The write path trusts more of its caller than the read path.** Participants, a carry-out's memory type and a note's location come from whoever calls memgate. That is fine while the caller is the trusted host passing true context; verifying it is deferred to the Ranch integration. Since 2026-09-30, write authorisation is in Cedar and proved, the high-assurance write seal holds whatever the caller claims, and a carry-out is only allowed where its claimed source is readable.

## The contract with the host

Ranch agents will run as their own processes with tool and network access (Gus, 2026-09-30). So the host can't simply make every memory call on an agent's behalf. Two things have to be verified before a call reaches memgate:
- **Who is calling (authentication).** Per-agent credentials, so an agent can't act as another.
- **What context it is in (attestation).** Location and participants, vouched for by the host, the only party that knows them. A common form is a short-lived context token signed by the host (agent, location, participants, conversation, turn, expiry) and bound to the agent's credential, reissued whenever the agent moves.

**This is deferred to the Ranch integration** (Decision Log, 2026-09-30). The mechanism depends on how the Ranch identifies processes and connects them, and building it here would mean guessing that interface.

**What this repo guarantees in the meantime is a contract.** memgate trusts the agent, location and participants it is given. Whoever integrates it must deliver them verified. When that check is added, it goes where memgate turns a request into a context:
- the `Context` every client method takes (since 0.2.0): the host builds it, and that is where verification happens before any memgate call;
- the validator's `_caller`, which today trusts the agent and location headers once the shared secret checks out.

The Cedar policies, the label derivation and the proofs are unchanged by it: they already decide on a given context.

## Hardening proposals

Decisions of 2026-09-30. Items 2 and 3 are accepted and implemented (2026-09-30), and proved ([[memgate Proofs]] C4, W1–W6).
1. **Verified context (deferred to Ranch integration).** As in the contract above.
2. **Carry-out authorised in Cedar with a location (done).** The Cedar carry-out decision gains the current location and requires it to hold every one of the source's location labels, so a carry-out is only authorised where its source is readable. SymCC can then prove it. Taking the source itself from verified context, rather than from the caller, is deferred with item 1.
3. **High-assurance seal on writes, in Cedar (done).** Every write made in a high-assurance location must carry that location's label. That covers personal memory, notes and carry-outs alike. Moving write authorisation into Cedar (a `write` action with the current location) puts this under the proofs: nothing written inside a high-assurance location is ever readable outside it.
4. **Who classifies memory type (decided: the agent's own claim, audited).** Trusted under the cooperative threat model. The audit log records the claimed type with every carry-out decision. Revisit at Ranch integration: the alternatives are the host, an independent classifier (an LLM, which makes it a judgement call again), or the most restrictive type unless verified. Selective environments are only as strong as this choice.

## Agents' own actions: leakage the memory service can't see

memgate controls what an agent can *recall*. It can't control what an agent *does* with what it legitimately knows. Take Gus's example: an agent in the vault writes a secret to a file, then reads the file after leaving. The secret has left the vault without memgate ever being asked. Every channel like this is outside a memory service, and they come in two groups.

**Channels an agent can act through:**
- **Working context.** An LLM's context window holds whatever it recalled. If the same context follows an agent out of a location, the recall filter never gets a say.
- **Tools with side effects.** Files, databases, code execution, the web, email or messages: anything that persists or sends.
- **Other agents.** Telling another agent is retelling, which the label model governs only for what goes into memory, not for what is said.
- **Content encoded in permitted output.** A permitted carry-out or message can carry more than it appears to.

**Channels that come with the platform:**
- **The simulation's own records.** Logs, traces and transcripts written by the host. Our gateway logs request metadata only, not prompts. Hindsight's LLM trace is off, its log level is warning and recall queries are redacted from its log (memgate 0.4.2). memgate's provenance log keeps high-assurance records in a separate partition.
- **The model provider,** which sees every prompt.

We can't solve these by building only the memory service. All of this is deferred to the Ranch integration (Decision Log, 2026-09-30). But the same model extends past memory, and memgate can supply the pieces.

**What the host (Knowledge Ranch) has to do:**
- Clear or seal an agent's working context when it leaves a location, above all a high-assurance one.
- Scope every tool by the agent's context. The simplest version applies the same labels to storage: files written in a location get that location's labels, and are readable where memgate would allow. Tools that send outward are off inside high-assurance locations.
- Treat logs, traces and transcripts as labelled data, stored per high-assurance partition like memgate's provenance log.

**What memgate can offer:**
- Its label sets, its Cedar policy and its provenance log, as the shared vocabulary for everything above.
- An idea worth deciding: a **context taint** query. Provenance already records every recall. For any agent-turn, memgate could report the union of the labels of what was recalled. The host could then refuse any action (tool call, file write, message, move to another location) whose destination couldn't hold those labels. That is information-flow control over the agent's whole working context, with the memory service as its source of truth.
