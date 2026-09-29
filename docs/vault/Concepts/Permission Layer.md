---
type: design
status: draft
authority: describes
summary: "Design of the permission layer (working name memgate): a system-agnostic core (label-set registry, Cedar policies, allowed-ID resolution, write labelling, derivation rules, cross-agent provenance, audit) plus a thin adapter per memory system, Hindsight first. Built on Cedar and the memory system's own storage; conceptually a special case of the Decentralized Label Model."
created: 2026-09-29
updated: 2026-09-29
tags: [agentic-memory, design, permissions, memgate]
---

# Permission Layer

*Draft 2026-09-29. Implements the rules in [[Context-Scoped Memory Permissions]], [[Label and Memory Types]] and [[Label Rule Table]], with Cedar as the policy engine ([[Cedar]]). Rulings are in [[Decision Log]].*

**The idea.**
- **The core:** a small, memory-system-agnostic core decides what a context may read and write, labels everything written, and keeps derived memory within its label set.
- **Adapters:** each memory system gets a thin adapter that stores a label-set ID on every item and filters its search by a list of allowed IDs.
- **Reuse:** almost everything is prebuilt. Cedar does the policy work, and the memory system does storage, extraction, consolidation and search. The custom part is the glue.

## Not reinventing it: prior work

| Our rule | Established concept |
| --- | --- |
| Every identity and location label must be held | Security compartments in multilevel security (Bell–LaPadula, 1973) |
| A derived memory is readable only by those who could read every source (identity and location labels combine, participants intersect) | The Decentralized Label Model (Myers & Liskov, SOSP 1997): combining data narrows who may read the result |
| Labels travel with derived data | Information-flow control and taint tracking; FIDES and CaMeL apply them to LLM agents ([[Vector Store Label Filtering]]) |
| Labels stored with data and checked by the store | Row-level security; Accumulo cell visibility labels |
| Closest prior work in agent memory | [[Collaborative Memory]], Authorization Before Context, AkasicMEM |

**What's new:** the model is a special case of the Decentralized Label Model and will be cited as such. The contribution is applying it to agent memory's own processes (extraction, consolidation, retelling), plus the selective-memory framing and the benchmark.

## Prebuilt and custom

**Prebuilt, used as-is:**
- **Cedar:** the policy language, evaluator, partial evaluation, schema validation, and the analyser that proves the high-assurance seal.
- **The memory system:** storage, extraction, consolidation and search. For Hindsight, that includes its tag filter inside the search, its validator hook, and tenant schemas.
- **SQLite or Postgres** for the label-set table.

**Custom** (estimated 800–1,200 lines of Python, ~60 lines of Cedar, plus tests):

| Component | Does |
| --- | --- |
| Label-set registry | Canonicalises a label combination to one stable ID; records the high-assurance locations it contains (Cedar can't loop over set members, so this is precomputed) |
| Policies | The Cedar schema and policies: the read rule (identity and location held, reader among the participants), the high-assurance seal, environment write rules (open, selective, *Severance*) |
| Allowed-ID resolver | Context → allowed label-set IDs. Start by checking every label set with Cedar (fine at simulation scale). Later, compile Cedar's residual into a query over the table; Cedar ships no such translator |
| Write labeller | A new memory's labels come from the context: location, participants, and the author for personal memory. Writes into personal memory go through Cedar's writePersonal rule |
| Derivation guard | Consolidation, merging and dedup stay within one label set. The only way across is an explicit, environment-approved relaxation into personal memory, which is logged |
| Provenance log | When an agent speaks, records which memories it recalled, so memories formed from what it said can cite them. No memory system does this across agents |
| Audit | Every allowed-ID decision, write and relaxation; plus the side-effect check for high-assurance recall |

## Architecture

**Two layers of enforcement:**
- **The core is the only way into memory.** Agents never call a memory system directly. The same pattern works for every system.
- **The system's own hook, where one exists, is a second lock.** Hindsight's validator overwrites every recall's tags with the allowed IDs, so even a direct call is filtered.

**Adapter contract.** For a system to be supported, it must:
1. **Store an opaque label-set ID** on every item, as a tag, metadata field or namespace.
2. **Filter search by a list of IDs inside the query.** Fallback: one partition per ID and a search of each.
3. **Keep consolidation within one ID,** by configuration or a hook, or have it switched off.
4. **Recall without side effects,** where configurable (logs, usage counts, recency).
5. **Report which sources a derived item came from.** Optional, but used for audit.

**How well each system fits:**

| Level | Meaning | Systems |
| --- | --- | --- |
| A: native | ID filter inside the search | [[Hindsight]]; [[Redis Agent Memory]] V0; [[Mem0]] once its add-time lookup is fixed |
| B: partitioned | One partition per label set, a search of each | AWS AgentCore, [[Cognee]], a directory per label set in [[Letta]] |
| C: not supported | No stable place for an ID, or merges across sets | [[Zep and Graphiti]] without a deep fork |

**The Hindsight adapter** is the only Hindsight-specific part:
- label-set ID as the item's single tag;
- a validator extension injecting the allowed IDs as `any_strict` (recall), and checking tags on retain;
- the default "combined" observation scope, with the widening scope modes refused;
- a tenant schema per high-assurance location;
- the LLM-request and audit logs off in high-assurance partitions;
- the graph search arm, which filters after scoring, disabled or patched.

**Conformance tests.** Selective-memory suites S1–S3 from [[Benchmark Plan]] run against every adapter:
- witness recall;
- the {A,B}, {A,C}, {A,B,C} case;
- retelling.

A new system is supported when its adapter passes them. The same suites become the start of the published benchmark.

## Layout

A top-level package, **memgate/** (working name), beside benchmark/, with its own pyproject:
- `memgate/core/`: registry, policies and Cedar glue, resolver, labeller, derivation guard, provenance, audit;
- `memgate/adapters/hindsight/`: the adapter;
- `memgate/tests/`: including the S1–S3 conformance suite.

The benchmark imports memgate; memgate never imports the benchmark.

## Build order

1. Label-set registry and Cedar policies, with tests.
2. Allowed-ID resolver, with a Cedar proof of the high-assurance seal.
3. Write labeller and derivation guard.
4. Hindsight adapter: validator extension, tags, scopes, tenant schema.
5. Provenance log and audit (built 2026-09-29, see [[memgate Core]]).
6. S1–S3 conformance suite against Hindsight, with a no-filter baseline to show the tests catch leaks.

## Open questions

- [ ] How many label sets a long simulation produces, which decides when the residual-to-query compiler is needed.
- [ ] The API for recording which memories an agent recalled when speaking: in memgate, or in the host application (CHORUS)?
- [ ] Hindsight's reflect: the validator can't force reflect's tag scope, so the adapter must always pass it (or reflect is disabled).
