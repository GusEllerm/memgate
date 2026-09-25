---
type: reference
status: active
authority: reference
summary: "Coverage check of popular agent memory systems as of 2026-09-25: open-source systems ranked by stars and downloads (checked via APIs), with triage against our model. Scoping and lineage notes are unverified background knowledge; benchmark scores are vendor claims only."
created: 2026-09-25
updated: 2026-09-25
tags: [agentic-memory, reference, survey, landscape]
---

# Memory System Landscape

*Coverage check, 2026-09-25, per [[Decision Log]]. Five systems were later verified against their code (section below). Stars, last commit, licence and language come from the GitHub API; downloads from pypistats.org and the npm API, all checked on that date. **The family, scoping, lineage and claims columns are unverified background knowledge** (planned verification did not complete) and are leads for deep dives, not findings. Benchmark scores are self-reported and unverified; per [[Evaluation Criteria]] they are not scored until we benchmark ourselves. Managed services are listed separately below. Full reviews are linked from [[Architecture Survey]].*

**What stands out.**
- **Downloads and stars disagree.** Hindsight, LangMem, Honcho, OpenViking and ReMe are used far more than their stars suggest. gbrain, agentmemory, TencentDB Agent Memory and context-mode have large, recent star counts with little download evidence; treat those as possibly inflated.
- **New cluster: memory for coding agents** (claude-mem, agentmemory, engram, context-mode, basic-memory). Single-user and per-project, with no notion of labels. A poor fit.
- **The "memory OS" systems repeat the survey's main risk** (MemOS, EverOS, MIRIX, MemoryOS, OpenViking). They build store-wide or per-directory summaries or profiles, and some update state on recall (heat, decay). That breaks side-effect-free recall.
- **Dormant or dead:** Motorhead, Second Me, A-MEM, Memobase and Kernel Memory.

## Open-source systems

Popularity score = stars + monthly downloads ÷ 20. † = general framework; its figures cover the whole framework, not only the memory module. "Alive" means a commit to the default branch after 2026-06-25.

| # | System | ★ | Downloads/mo | Last commit | Licence | Family (unverified) | Triage |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | [LlamaIndex memory](https://github.com/run-llama/llama_index)† | 52.3k | 6.6M | 2026-09-25 | MIT | Hybrid memory blocks | Weak: a toolkit, not a store |
| 2 | [Mem0](https://github.com/mem0ai/mem0) | 66.0k | 2.44M | 2026-09-25 | Apache-2.0 | Extracted facts | **Surveyed:** [[Mem0]] |
| 3 | [CrewAI memory](https://github.com/crewAIInc/crewAI)† | 59.0k | 2.44M | 2026-09-25 | MIT | Vector RAG + entities | Skip |
| 4 | [claude-mem](https://github.com/thedotmack/claude-mem) | 94.7k | 71k | 2026-09-25 | Apache-2.0 | Session compression | Weak: single-user coding tool |
| 5 | [Hindsight](https://github.com/vectorize-io/hindsight) | 28.9k | 1.06M | 2026-09-25 | MIT | Fact, experience and observation networks + graph | **Strong candidate** (verified below) |
| 6 | [Graphiti](https://github.com/getzep/graphiti) | 31.2k | 610k | 2026-09-24 | Apache-2.0 | Temporal knowledge graph | **Surveyed:** [[Zep and Graphiti]] |
| 7 | [OpenViking](https://github.com/volcengine/OpenViking) | 38.7k | 441k | 2026-09-25 | AGPL-3.0 | File-based context database, tiered | **Deep-dive candidate** (verified below) |
| 8 | [Supermemory](https://github.com/supermemoryai/supermemory) | 30.9k | 461k | 2026-09-23 | MIT | Extracted facts + graph; engine mostly hosted | Weak: core is closed |
| 9 | [Letta](https://github.com/letta-ai/letta-code) | 28.3k | 360k | 2026-09-25 | Apache-2.0 | Tiered / file-based | **Surveyed:** [[Letta]] |
| 10 | [Honcho](https://github.com/plastic-labs/honcho) | 7.3k | 767k | 2026-09-25 | AGPL-3.0 | Extracted facts about peers; per-observer views | **Deep dive** |
| 11 | [Semantic Kernel](https://github.com/microsoft/semantic-kernel) / Kernel Memory† | 28.6k / 2.2k | 285k | 2026-09-19 / 06-08 | MIT | Vector RAG | Skip (Kernel Memory dormant) |
| 12 | [LangMem](https://github.com/langchain-ai/langmem) | 1.7k | 700k | 2026-09-09 | MIT | Extracted facts over LangGraph's store | Weak: search refreshes TTL, no lineage (verified below) |
| 13 | [Cognee](https://github.com/topoteretes/cognee) | 31.0k | 89k | 2026-09-24 | Apache-2.0 | Knowledge graph + vector; per-dataset access control | **Deep dive** |
| 14 | [gbrain](https://github.com/garrytan/gbrain) | 30.3k | – | 2026-09-25 | MIT | Markdown "brain" | Skip |
| 15 | [agentmemory](https://github.com/rohitg00/agentmemory) | 28.8k | – | 2026-09-25 | Apache-2.0 | Coding-agent memory | Skip |
| 16 | [TencentDB Agent Memory](https://github.com/TencentCloud/TencentDB-Agent-Memory) | 27.3k | – | 2026-09-24 | Not stated | Hybrid, team-shared | Weak: tied to TencentDB |
| 17 | [context-mode](https://github.com/mksglu/context-mode) | 24.1k | – | 2026-09-24 | Not stated | Context optimiser | Skip: not a memory store |
| 18 | [Zep](https://github.com/getzep/zep) | 4.9k | 256k | 2026-09-18 | Apache-2.0 | Knowledge graph | **Surveyed:** [[Zep and Graphiti]] |
| 19 | [Memori](https://github.com/MemoriLabs/Memori) | 16.9k | 20k | 2026-09-18 | Not stated | SQL-native facts | Weak |
| 20 | [memvid](https://github.com/memvid/memvid) | 16.6k | 1k | 2026-07-14 | Apache-2.0 | Single-file archive | Skip |
| 21 | [Second Me](https://github.com/mindverse/Second-Me) | 15.7k | – | 2025-09-19 | Apache-2.0 | Personal model training | Skip: dormant |
| 22 | [ReMe](https://github.com/agentscope-ai/ReMe) (was MemoryScope) | 3.5k | 230k | 2026-09-24 | Apache-2.0 | Personal, task and tool memories | Weak |
| 23 | [memU](https://github.com/NevaMind-AI/memU) | 14.4k | 2k | 2026-09-21 | Not stated | File/category facts | Weak |
| 24 | [EverOS](https://github.com/EverMind-AI/EverOS) (was EverMemOS) | 13.2k | 21k | 2026-09-24 | Apache-2.0 | Markdown source of truth; memory cells → episodes and facts | **Deep-dive candidate** (verified below) |
| 25 | [txtai](https://github.com/neuml/txtai) | 13.0k | 13k | 2026-09-25 | Apache-2.0 | Vector + graph store | Weak: a store, not a memory system |
| 26 | [MemOS](https://github.com/MemTensor/MemOS) | 11.6k | ~1k | 2026-09-22 | Apache-2.0 | Tiered OS-style (MemCube) | Weak: search writes usage records (verified below) |
| 27 | [LongMemory](https://github.com/CaviraOSS/LongMemory) (was OpenMemory) | 4.5k | 56k | 2026-09-20 | Apache-2.0 | Hierarchical sectors + decay | Skip: decay changes state on recall |
| 28 | [engram](https://github.com/Gentleman-Programming/engram) | 6.8k | – | 2026-09-25 | MIT | SQLite full-text | Skip |
| 29 | [MemoryBear](https://github.com/SuanmoSuanyangTechnology/MemoryBear) | 6.8k | – | 2026-09-24 | Apache-2.0 | Graph + forgetting | Skip |
| 30 | [basic-memory](https://github.com/basicmachines-co/basic-memory) | 4.0k | 29k | 2026-09-24 | AGPL-3.0 | Markdown files + SQLite (MCP) | Weak |
| 31 | [MIRIX](https://github.com/Mirix-AI/MIRIX) | 3.4k | <1k | 2026-08-20 | Apache-2.0 | Tiered, six memory types | Weak |
| 32 | [MemMachine](https://github.com/MemMachine/MemMachine) | 3.2k | – | 2026-09-24 | Apache-2.0 | Episodic + profile | Weak |
| 33 | [Memobase](https://github.com/memodb-io/memobase) | 2.9k | 3k | 2026-01-11 | Apache-2.0 | Profile + events | Skip: dormant |
| 34 | [MemoryOS](https://github.com/BAI-LAB/MemoryOS) | 1.6k | <1k | 2026-07-07 | Apache-2.0 | Short/mid/long-term tiers | Skip: "heat" updated on recall |
| 35 | [A-MEM](https://github.com/agiresearch/A-mem) | 1.2k | <1k | 2025-12-12 | MIT | Zettelkasten notes | Skip: dormant; borrow ideas |
| 36 | [Motorhead](https://github.com/getmetal/motorhead) | 0.9k | – | 2025-06-10 | Apache-2.0 | Session summaries | Skip: dead |
| 37 | [Redis Agent Memory Server](https://github.com/redis/agent-memory-server) | 0.3k | <1k | 2026-09-18 | Apache-2.0 | Vector RAG | **Surveyed:** [[Redis Agent Memory]] |
| – | [Falda](https://github.com/rbross-hpc/falda) (Rob Ross's fork) | – | – | 2026-09-05 | Apache-2.0 | Tiered (TypeScript, SQLite) | **Surveyed:** [[Falda]] |

**Renames seen:** GibsonAI/memori → MemoriLabs/Memori, modelscope/MemoryScope → agentscope-ai/ReMe, EverMemOS → EverMind-AI/EverOS, CaviraOSS/OpenMemory → LongMemory.

**Vendor benchmark claims (self-reported, unverified, not scored):**
- Mem0: LoCoMo 92.5, LongMemEval 94.4.
- Hindsight: LongMemEval about 91%.
- Supermemory: LongMemEval about 82%.
- memU and EverOS: LoCoMo about 92%.
- MIRIX: LoCoMo about 85.
- Memobase: LoCoMo about 76.
- MemOS: LoCoMo 73–75.
- Zep/Graphiti: DMR 94.8.

## Verified against code (17 systems)

*Three late verification passes read the source of seventeen systems on 2026-09-25. File paths are given; the benchmark figures are self-reported. Rows not listed here remain unverified.*

| System | Filter inside retrieval | Lineage | Search side effects | Access control | Claims (self-reported) | Revised triage |
| --- | --- | --- | --- | --- | --- | --- |
| Honcho | Mostly: pgvector is one SQL statement (crud/document.py); on external vector stores, some filters are applied after top-k | **Yes**: a document-sources table records "derived from" links, with a tool to walk the reasoning chain (models.py) | None: the dialectic tools are read-only; reinforcement counts only at write time | JWT claims for admin, workspace, peer and session (security.py), **off by default** | LongMemEval-S 90.4–92.6%, LoCoMo 89.9% ([blog](https://plasticlabs.ai/blog/research/Benchmarking-Honcho)) | Reviewed: [[Honcho]] |
| EverOS | **Yes**: owner, app and project are always injected and callers cannot override them; LanceDB filters before ranking (backends/lancedb.py) | **Yes**: episodes and facts carry their source memory cell (tables/episode.py, atomic_fact.py) | **None**: "The manager never writes to storage" (search/manager.py) | None: local-first | LoCoMo 94.42, LongMemEval 94.00 (benchmarks/README.md) | **Promoted to deep-dive candidate.** Offline "reflection" merges episode clusters, which needs checking for label mixing |
| MemOS | Yes: Neo4j filters first (graph_dbs/neo4j.py) | Yes: source messages and version history (memories/textual/item.py) | **Yes**: every search appends a usage record to each returned node (searcher.py) | Roles, plus cube-level read/write sharing | LoCoMo 88.83, LongMemEval 89.20 (README) | Weak: search writes state |
| Memori | Partly: SQL scopes by entity, but the candidate pool is capped by recency and frequency before ranking, so older facts can silently drop out | Partial: to the conversation, not the message | Minor upserts | Entity scope only | LoCoMo 87% ([benchmark](https://memorilabs.ai/benchmark)) | Weak |
| memU | Yes on pgvector (one statement); brute force on SQLite | **None**: files link to nothing upstream | None seen | Scope fields only | None current | Weak: no lineage |
| Hindsight | **Yes**: bank, tag and time filters inside each HNSW search (engine/search/retrieval.py) | **Yes**: consolidated observations store their source memory IDs and a proof count (engine/consolidation/consolidator.py) | None found; mental models refresh in the background | Banks isolate strictly; a tenant extension gives each tenant its own Postgres schema | LongMemEval-S 94.6%, LoCoMo 92% ([benchmarks](https://benchmarks.hindsight.vectorize.io/)) | **Strong candidate**, reviewed: [[Hindsight]] |
| Cognee | By database choice, not a filter: with backend access control, one graph and vector database per dataset, and search runs separately in each readable dataset (modules/search/methods/search.py) | **Yes**: every data point records its source pipeline, task, node set, user and content hash (engine/models/DataPoint.py) | **Yes**: every search logs the query and answer to search history | Users, tenants, roles; per-dataset read/write/delete/share. Permission failures return an empty list | BEAM 100K 0.79, 10M 0.67 (README warns the runs are small) | Reviewed: [[Cognee]] |
| OpenViking | **Yes**: tenant, access-list and path scope are combined into the vector search call (storage/viking_vector_index_backend.py) | Partial to yes: each session commit writes a memory diff linking the archived messages to what changed | Probable: a usage count feeds a "hotness" score (the code that increments it was not found) | Tenants, roles (ROOT reaches every tenant), optional per-directory and per-file access lists | LoCoMo 80.3–82.9% (README) | **Deep-dive candidate**: a close fourth; AGPL |
| LangMem | Yes on the Postgres store; the in-memory store filters in Python | None for long-term memories | **Yes**: searches refresh TTL by default, updating the rows returned | None | None from the vendor; the Mem0 paper measured 58.10% on LoCoMo ([arXiv](https://arxiv.org/html/2504.19413)) | Weak |
| Supermemory | Container tags are hashed into separate namespaces, so that scope applies before search; metadata filter placement is unknown | Partial: update/extend/derive relations and history | Background "dreaming" | API keys scoped to container tags, read or write | LongMemEval 95% Recall@15 and 97% Recall@20; recall figures, not QA accuracy | Weak: the memory engine is closed source |
| MIRIX | **Yes**: SQL filters on user, organisation and filter tags, including a read-scope IN list, before ranking; caller-supplied scope keys are ignored (services/episodic_memory_manager.py, database/filter_tags_query.py) | Partial: a free-text source field, no foreign key to messages | None seen; "dream" consolidation only when called | Per-client write scope and read scopes | LoCoMo 85.4% ([paper](https://arxiv.org/abs/2507.07957)) | Worth noting: the read-scope IN list is our label-set-ID filter shape; weak lineage |
| MemMachine | Mixed: sessions are separate Neo4j labels; property filters are applied **after** ANN (fetches 4× the limit, falling back to an exact scan) | **Yes**: derived-from edges to episodes, and citations on semantic features | Unknown | Org, project, group, agent, user, session | LoCoMo 0.917, LongMemEval-S 93.0% ([paper](https://arxiv.org/abs/2604.04853)) | Weak: post-filtering can silently drop recall |
| Memobase | Yes: SQL scopes by user and project with cosine ordering | Partial: gists link to events; profiles don't link to source chats | None found | Per-project tokens | LoCoMo 75.78% | Skip: dormant |
| ReMe | Yes in the local store: path, date and tag filters before scoring | Partial: daily notes link to the source conversation | None on search; consolidation on cron | Workspace directory only | LongMemEval 89.4%, BEAM 65–66% | Weak: **the tag filter fails open**, returning unfiltered results if the tag index is unhealthy |
| MemoryBear | Partly: Neo4j WHERE then cosine in Python, with a loop that silently breaks on errors; full-text filters after the index | Likely | Usage-based activation is coded but switched off; nightly reflection and forgetting mutate memory | Tenant, workspace, end user | About 73–75% (dataset unnamed) | Skip: **ships default admin credentials** |
| MemoryOS | Physical: one directory per user | None | **Yes**: search increments visit counts and "heat", then saves | Filesystem path only | LoCoMo relative gains only ([paper](https://arxiv.org/abs/2506.06326)) | Skip |
| A-MEM | None: one hard-coded collection, queries with no filter | None: evolution rewrites neighbouring notes without provenance | None | None | LoCoMo per-category F1 only ([paper](https://arxiv.org/abs/2502.12110)) | Skip: not multi-tenant |

## Recommended deep dives

*Reviews completed 2026-09-25: [[Hindsight]] (best fit), [[Honcho]], [[Cognee]].*

1. **Honcho.** Each participant (peer) keeps its own view of the others, e.g. "what B concluded about A". That is the closest built-in analogue to our participant labels. It runs on Postgres with pgvector, so filtering inside the search should be natural, and downloads are high. AGPL licence.
2. **Hindsight.** Second only to Mem0 in downloads among dedicated memory systems. Observations and opinions are consolidated from facts, which tests our union-inheritance rule. Its memory banks and tags look like hooks for labels.
3. **Cognee.** The only popular store with real per-dataset access control (read, write, share, and a separate database per dataset). It is the nearest existing permission layer to compare with our partitions.

**Next in line:** OpenViking and EverOS, both promoted after the code checks above.

## Managed services

*Read from the linked docs on 2026-09-25 unless marked (u), meaning seen only in a search snippet. Rankings are by prominence (judgement). Rows marked "prior" come from earlier reviews.*

**The general problem.** Every service that extracts memories on its own servers does so inside a single partition key (namespace, scope, container or store). So none can give a derived memory the union of its sources' labels.

The only safe pattern is to **make the partition key the label-set ID**. Extraction then never crosses label sets and the union rule holds trivially, but nothing can be synthesised across label sets.

The recurring gap is "any one participant". An agent's readable label sets form a list of IDs, and no service supports OR over partitions inside vector search. So recall would be one query per readable label set, merged by us.

| # | Service | Status | Memory model | Scoping and authorisation | Filter inside retrieval | Lineage | Triage |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | [AWS Bedrock AgentCore Memory](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/memory.html) | GA 2025-10 (u); priced per event and per stored record (u) | Short-term events; long-term records from strategies: semantic, summary, preference, episodic, override, self-managed. Superseded records are marked invalid | [Namespace templates](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/specify-long-term-memory-organization.html) from actor, session and up to 5 custom variables. IAM conditions on reads (namespace path) and writes (namespace variables) | Yes, [metadata filters before k-NN](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/long-term-memory-metadata.html). But AND only, equality only, at most 5. "Strictly consistent" keys (at most 3) stop extraction merging across values | Namespace and timestamps; link to source events not documented | **Deep dive candidate** |
| 2 | [Google Memory Bank](https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/memory-bank) (Vertex / Gemini Enterprise Agent Platform) | Preview 2025-07, now GA | Gemini extracts and consolidates per scope; profiles, TTL | Exact-match scope dict; [IAM condition on scope](https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/memory-bank/iam-conditions), but not on multi-scope list or purge | Scope is an exact partition; metadata filters [don't work with similarity search](https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/memory-bank/fetch-memories) | [Revisions](https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/memory-bank/revisions) keep the extracted text, with no link to the source session | Runner-up |
| 3 | Mem0 Platform | prior | Extracted facts | User, agent and run IDs plus filters | Yes (OSS) | None | Weak: fork the OSS instead ([[Mem0]]) |
| 4 | [Microsoft Foundry memory](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/what-is-memory) | Preview | Profile, chat summary, procedural | [One scope string](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/memory-usage); RBAC per store; at most 100 scopes per store | Scope only | None documented | Weak |
| 5 | [Claude Managed Agents memory stores](https://platform.claude.com/docs/en/managed-agents/memory) | Beta | Files mounted into the session. The agent writes them; no server-side extraction. Optional "dreaming" writes to a new store | Up to 8 stores per session, each read-only or read-write, enforced by the filesystem | Nothing to filter: visibility is fixed when the session starts; search is grep, not vector | Every write is an immutable version attributed to its session | **Deep dive candidate** |
| 5b | [Claude API memory tool](https://platform.claude.com/docs/en/agents-and-tools/tool-use/memory-tool) | Available | File commands our own handler executes | Ours | Ours | Ours | Not a service: a possible agent-facing interface to our own store |
| 6 | Zep Cloud | prior | Temporal knowledge graph | group_id | Vector yes; graph walks check only their end nodes | Partial | Weak ([[Zep and Graphiti]]) |
| 7 | [LangGraph Platform store](https://reference.langchain.com/python/langgraph-sdk/auth/Auth/on) | GA (not re-verified) | Namespaced key-value store plus embeddings; extraction client-side | Namespace tuples; an auth hook can rewrite namespaces | Filter placement unconfirmed | Ours | Only if we want a hosted store. TTL refresh on search is a side effect |
| 8 | Letta Cloud | prior | Git-backed Markdown | Per agent | Closed | Git history | Weak ([[Letta]]) |
| 9 | [Supermemory](https://supermemory.ai/docs/concepts/filtering.md) (hosted) | GA | Memory graph; background "dreaming" [derives new facts](https://supermemory.ai/docs/concepts/graph-memory.md) across a container | One container tag per search | Placement not stated | Update history, source documents | Skip: derived facts can't carry correct labels |
| 10 | OpenAI | – | No hosted long-term memory API verified. The [Agents API](https://developers.openai.com/api/docs/guides/agents-api/overview) keeps session state; [SDK memory](https://openai.github.io/openai-agents-python/sandbox/memory/) is client-side files | – | – | – | Skip |
| 11 | Redis Agent Memory (Iris) | prior: preview | Extracted | Store plus a caller-supplied owner | Unconfirmed | – | Weak; the V0 fork is viable ([[Redis Agent Memory]]) |
| 12 | [Databricks agent memory](https://docs.databricks.com/aws/en/agents/agent-memory/managed-memory) | Beta | Path/content entries written by tools | Partitioned by actor, but anyone who can reach a store can read every actor's entries | BM25 only | Optional session | Skip |
| 13 | [Neo4j Agent Memory Service](https://neo4j.com/blog/genai/a-tour-of-the-neo4j-agent-memory-service-nams/) | Labs, experimental | Graph of messages, entities and reasoning traces | Per-user workspaces | Unknown | Entities traced to messages | Weak: shared entity nodes |
| – | Snowflake, MongoDB | Product feature only (u); partner sample only (u) | – | – | – | – | Skip |

**Vendor benchmark claims (self-reported, unverified, not scored):**
- AgentCore: LoCoMo 70.6%, LongMemEval-S 73.6% ([AWS blog](https://aws.amazon.com/blogs/machine-learning/building-smarter-ai-agents-agentcore-long-term-memory-deep-dive/)). Its own RAG baseline scored higher on LoCoMo, at 77.7%.
- Supermemory: 97% Recall@20 on LongMemEval-S ([research](https://supermemory.ai/research)). This is a retrieval score, not question-answering accuracy.

**Recall side effects.**
- None apparent: AgentCore retrieve, Memory Bank retrieve and read-only Claude store mounts.
- Present: LangGraph's TTL refresh on search and Supermemory's background dreaming.

**Deep-dive candidates** (not yet started; hosted services raise the question of whether hosted is acceptable at all):
1. **AgentCore Memory.** The only managed service with all four of:
   - extraction that never merges across a key;
   - pre-filters inside k-NN;
   - IAM conditions on reads and writes;
   - a self-managed extraction option.

   Open questions: are records linked to their source events, how does it handle ORing many label-set IDs, and what are the key and filter limits?
2. **Claude Managed Agents memory stores.** Nothing is extracted server-side, and the stores a session sees are fixed when it starts. That makes union inheritance, provenance and read-only recall enforceable. Limits: beta; 8 stores per session; 10,000 memories per store; no semantic search.

## Sources

- Metrics: GitHub REST API, [pypistats.org](https://pypistats.org) and the npm downloads API, all queried 2026-09-25.
- Discovery: [TeleAI-UAGI/Awesome-Agent-Memory](https://github.com/TeleAI-UAGI/Awesome-Agent-Memory).
