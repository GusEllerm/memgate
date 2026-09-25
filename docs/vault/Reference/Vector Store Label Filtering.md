---
type: reference
status: active
authority: reference
summary: "How eight vector stores filter nearest-neighbour search by label: when the filter runs, whether 'all of an item's labels are allowed' is expressible, and what derived-data leakage research says about embeddings and summaries."
created: 2026-09-25
updated: 2026-09-25
tags: [agentic-memory, reference, survey, vector-store]
---

# Vector Store Label Filtering

*Surveyed 2026-09-25 from vendor docs and papers (all pages opened are linked). Facts are as of that date. Feeds [[Architecture Survey]] and [[Label Rule Table]].*

**Verdict so far.** Any of these stores can serve as the memory layer if the filter runs inside the search. The label check we need is "all of an item's labels are allowed". Only pgvector (a native subset operator) and Qdrant (a negated "except" match) express it directly. Every store can express it through **label-set IDs**: give each distinct stored label set an ID, and have the policy list the IDs whose sets are allowed. Embeddings must be treated as sensitive as the text they encode.

## Filtering by store

| Store | When the filter runs; a tight filter | Any label allowed | All labels allowed | Tenancy |
| --- | --- | --- | --- | --- |
| [pgvector](https://github.com/pgvector/pgvector) + [RLS](https://www.postgresql.org/docs/current/ddl-rowsecurity.html) | After the index scan: at the default ef_search of 40, a 10% filter returns about 4 rows. Iterative scan (capped at 20k tuples by default), partial indexes or partitioning fix it | labels && allowed | **Native**: labels <@ allowed ([array ops](https://www.postgresql.org/docs/current/functions-array.html)) | Partitions, partial indexes |
| Qdrant ([filtering](https://qdrant.tech/documentation/concepts/filtering/), [indexing](https://qdrant.tech/documentation/concepts/indexing/)) | During the search: filterable HNSW with extra payload edges; a planner switches to full scan when few rows match; optional ACORN | match any | **Native by negation**: must_not with "except allowed". Unlabelled items pass | Tenant index field, per-tenant HNSW, shard keys ([multitenancy](https://qdrant.tech/documentation/guides/multitenancy/)) |
| Weaviate ([filtering](https://docs.weaviate.io/weaviate/concepts/filtering)) | Before the search: allow-list from the inverted index, then ACORN (default since 1.34); flat search when fewer than about 15% match | ContainsAny | ContainsNone over the forbidden set | One shard per tenant, one tenant per query ([multi-tenancy](https://docs.weaviate.io/weaviate/manage-collections/multi-tenancy)) |
| Milvus ([filtered search](https://milvus.io/docs/filtered-search.md)) | Before the search by default; iterative filtering optional | ARRAY_CONTAINS_ANY ([array ops](https://milvus.io/docs/array-operators.md)) | NOT contains-any over the forbidden set | Database 64, collection 65k, partition 1,024, partition key in the millions ([multi-tenancy](https://milvus.io/docs/multi_tenancy.md)) |
| Pinecone ([metadata filter](https://docs.pinecone.io/guides/search/filter-by-metadata)) | Narrows candidates before scoring; can return fewer than top_k | $in | $nin over the forbidden set (check list semantics first) | Namespaces, one per query ([multitenancy](https://docs.pinecone.io/guides/index-data/implement-multitenancy)) |
| Chroma ([metadata filter](https://docs.trychroma.com/docs/querying-collections/metadata-filtering)) | Not documented | $or of $contains | $and of $not_contains per forbidden label | Not checked |
| LanceDB ([filtering](https://docs.lancedb.com/search/filtering)) | Before the search by default; very selective filters hurt recall (raise nprobes or bypass the index). Filtering after can return nothing | array_has_any | Untested workaround with array_has_all reversed; probably not indexed | Not checked |
| Redis QE ([vectors](https://redis.io/docs/latest/develop/ai/search-and-query/vectors/)) | A planner picks per query: iterative batches filtered after search, or exact brute force over the rows that match; it can switch mid-query | Tag match on any listed label | Negated tag match over the forbidden set | Key prefixes, separate indexes |

- **The complement problem.** Most stores need "no forbidden label", with forbidden = all labels − allowed. A newly created label stays readable until it is added to the full label list. Label-set IDs avoid this: the policy lists the allowed IDs and the query filters on ID IN [...]. Cost grows with the number of label sets actually in use, not with every possible combination.
- **Filtering after the search does not leak, but it loses recall.** pgvector's default and Redis's batched mode return too few results under tight filters.
- **Row-level security caveats.** RLS applies its policy before user conditions, except for leakproof functions. Superusers, BYPASSRLS roles and table owners (unless RLS is forced) skip it, and a table with no policy denies everything.
- **Partition per label set explodes combinatorially.** Namespaces and tenants allow one per query or have hard caps. They suit coarse axes like user or environment, not label sets. [HONEYBEE](https://arxiv.org/abs/2505.01538) (SIGMOD 2026) is a middle path: role partitions with selective replication, reported as 13.5x lower latency than RLS at 1.24x the memory.

## Derived-data leakage

| Source | Shows |
| --- | --- |
| [Vec2Text](https://arxiv.org/abs/2310.06816) (Morris et al., EMNLP 2023) | 92% of 32-token inputs recovered exactly from dense embeddings |
| [Song & Raghunathan 2020](https://arxiv.org/abs/2004.00053) | Embedding inversion (50–70% word F1), attribute inference and membership inference |
| [Huang et al., ACL 2024](https://aclanthology.org/2024.acl-long.230/) | Transferable inversion through a surrogate model, with no queries to the victim model |
| [Anderson et al.](https://arxiv.org/abs/2405.20446) | Membership inference against RAG databases through crafted prompts; instruction-based mitigation only partly works |
| [Zeng et al.](https://arxiv.org/abs/2402.16893) | RAG leaks its private retrieval database through generated output |
| [MEXTRA](https://arxiv.org/abs/2502.13172) (Wang et al.) | Black-box extraction of private records from agent memory |
| [Sun et al. 2026](https://arxiv.org/html/2606.21842) | Time-to-first-token timing leaks private prompt prefixes through KV-cache reuse |
| [SoK on RAG privacy](https://arxiv.org/pdf/2601.03979) (Bodea et al.) | Catalogues output, ranking and timing side channels (read only as a pointer) |
| [FIDES](https://arxiv.org/abs/2505.23643) (Costa et al.) | Agent planner that tracks confidentiality and integrity labels |
| [CaMeL](https://arxiv.org/abs/2503.18813) (Debenedetti et al.) | Capability-based data-flow policies; provably secure on 77% of AgentDojo tasks |
| [Permissive IFC](https://arxiv.org/abs/2410.03055) (Siddiqui et al.) | Labelling output with all input labels is over-conservative; labelling by the inputs that actually influenced it helps in over 85% of cases |

Further sources from a peer session's research, **not yet re-verified here**:

| Source | Shows (as reported) |
| --- | --- |
| [Collaborative Memory](https://arxiv.org/abs/2505.18279) (Rezazadeh et al. 2025) | Closest prior work: multi-user memory sharing with access control in agent memory. Read first |
| [Büttcher & Clarke, FAST'05](https://www.usenix.org/conference/fast-05/security-model-full-text-file-system-search-multi-user-environments) | Filtering search results after ranking leaks locked content through collection-wide ranking statistics |
| Qdrant multiple-partitions docs | Payload partitioning does not isolate sparse-vector IDF statistics |
| [Early Bird Catches the Leak](https://arxiv.org/abs/2409.20002) (2024) | Timing on shared KV or semantic caches leaks other users' prompts |
| [ConfAIde](https://arxiv.org/abs/2310.17884) (ICLR 2024) | GPT-4 leaks private information in context 39% of the time |
| [f-secure LLM system](https://arxiv.org/abs/2409.19091) (2024) | Information-flow control for LLM systems |
| [Permissioned LLMs](https://arxiv.org/abs/2505.22860) (2025) | Access control applied to the model itself |

Takeaways for our design:
- A derived item carries at least the union of its sources' labels, and is derived inside a context that unlocks all of them.
- A locked item's embedding is as sensitive as its text.
- Ranking statistics (e.g. keyword IDF) and caches must not be shared across contexts with different allowed sets. Otherwise locked content leaks through scores or timing even when it is filtered correctly (Büttcher & Clarke; Early Bird).

## For benchmarking later

- Bench each store with a tight filter (10% or less), not just a loose one, since that is where the stores differ.
- Report recall against an unfiltered exact baseline, and latency with label-set-ID filters versus native set operators.
