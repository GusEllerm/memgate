---
type: reference
status: active
authority: reference
summary: "Collaborative Memory (Rezazadeh et al., Accenture, 2025): provenance-checked private and shared memory tiers, with access from time-varying user–agent–resource graphs. Its read rule matches ours; its shared-write policy is an LLM declassifier and derived fragments can lose labels. No code released."
created: 2026-09-25
updated: 2026-09-25
tags: [memgate, reference, survey, prior-work]
---

# Collaborative Memory

*Surveyed 2026-09-25 from the paper's full text ([arXiv 2505.18279](https://arxiv.org/abs/2505.18279), v1, the only version), citing papers via Semantic Scholar, and a GitHub search. Facts are as of that date. Listed in [[Architecture Survey]].*

**Verdict so far.** The closest prior work on the access model. Its read rule is ours: a reader must hold every agent and resource a fragment carries, checked against current permissions at read time. It also treats provenance as first-class. But content reaches shared memory through an LLM told to strip user details, which makes the model a declassifier. And a derived fragment is tagged only with the resources used in that turn, so labels can be lost. Leakage is never measured, and the promised code is not released. Borrow the provenance and read rule; avoid the write path.

## What it proposes

- **Access model:** two time-varying bipartite graphs, users to agents and agents to resources (tools, knowledge bases).
- **Memory tiers:** each user has a private store. Each agent has a shared store of everything it produced for any user.
- **Provenance:** each fragment keeps immutable provenance: creation time, user, contributing agents, resources used.
- **Read rule:** a fragment is admissible if its agents and its resources are all currently allowed. Checking against the current graphs makes revocation retroactive.
- **Policies:** a read policy filters or transforms the admissible set. Two write policies (private and shared) turn an agent's output into fragments. Policies can be global, per user, per agent or time-varying.
- **Enforcement:** cosine top-k from the user tier plus top-k from the shared tier, restricted to fragments that pass the provenance check. Whether the check runs before or after the search is not stated. No label IDs, no partitioning.
- **Transforms:** done by prompts. In the experiments the read policy returns fragments verbatim, and the shared write policy is GPT-4o told to "Remove any user-specific details…".

## Fit with our model

| Aspect | Collaborative Memory | Ours |
| --- | --- | --- |
| Read rule | Every agent and resource on a fragment must be allowed | Every label type satisfied (all of identity and location; any of participants) |
| Revocation | Retroactive, checked against current graphs | Same: checked at read time |
| Provenance | Immutable per fragment: time, user, agents, resources | Required; also across agents |
| Crossing a boundary | LLM rewrites the content for shared memory | Only by an explicit environment rule, logged |
| Derived items | Tagged with resources used in that turn only; content read from memory can lose its labels | Union of every source's labels |
| User privacy | By which tier a fragment is in; the read rule never checks the user | By labels |
| Participants, locations, high assurance, export | Not covered | Core requirements |
| Goal | Share memory to save work | Selective memory for diverse opinions |

## Evaluation and maturity

- **MultiHop-RAG (5 users, 6 agents):** accuracy above 0.90, and up to 61% fewer resource calls than isolated memory at 50% query overlap.
- **200 synthetic business queries:** only a resource-usage histogram, with no ground truth.
- **SciQAG with access granted then revoked:** accuracy tracks access. An access matrix shows routing stays within the graph.
- **Leakage is never measured.** There is no adversarial test and no check that redaction worked. The access matrix shows correct routing, not an absence of leaks.
- **Code, license, maturity:** code promised but not found. The paper is CC BY-NC-ND 4.0, © Accenture, and a single v1 framework paper.

## Follow-up work to read next

Read from abstracts only; not yet verified in full.

| Paper | Relevance |
| --- | --- |
| Authorization Before Context ([arXiv 2608.17148](https://arxiv.org/abs/2608.17148)) | Each item records the audience present when it was recorded. It is admitted only if every current viewer was in that audience, checked on the assembled context and failing closed. Close to our participant labels when a memory is retold to a group |
| AkasicMEM ([arXiv 2609.25563](https://arxiv.org/abs/2609.25563)) | "Transitive lineage, policy composition during memory formation, re-evaluation at retrieval": our union inheritance |
| MemClaw ([arXiv 2606.24535](https://arxiv.org/abs/2606.24535)) | Names "provenance collapse" as a failure mode. Found scope enforced in search but bypassed when fetching by ID |
| GateMem ([arXiv 2606.18829](https://arxiv.org/abs/2606.18829)), No Attacker Needed ([arXiv 2604.01350](https://arxiv.org/abs/2604.01350)) | Retrieval-based memories still leak, and cleaning content at write time leaves residual risk |
| AIM ([arXiv 2609.12320](https://arxiv.org/abs/2609.12320)) | A private/public split at the index level, with an LLM deciding which is which |
| Artificial Selection ([arXiv 2605.04264](https://arxiv.org/abs/2605.04264)) | Treats memory governance as a selection regime. Relevant to our diversity goal |

## Borrow and avoid

**Borrow:**
- Immutable provenance per item (time, agents, sources) alongside labels.
- Read-time checks against current permissions, so revocation is retroactive.
- Their full, asymmetric and dynamic scenarios as a test layout.
- Resource-call reduction as a secondary metric.
- From Authorization Before Context: an all-viewers check when a memory is retold to a group, failing closed.
- From MemClaw: enforce labels on every read path (fetch by ID, export, summarisation jobs), not just search.

**Avoid:**
- LLM redaction as the way content crosses a boundary.
- Deriving labels from "resources used this turn".
- Relying on tier placement for identity.
- Treating routing matrices as evidence of no leakage. We need tests with planted canaries for laundering through derived memory and for retelling.
