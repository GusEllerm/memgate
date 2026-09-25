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

*Coverage check, 2026-09-25, per [[Decision Log]]. Stars, last commit, licence and language come from the GitHub API; downloads from pypistats.org and the npm API, all checked on that date. **The family, scoping, lineage and claims columns are unverified background knowledge** (planned verification did not complete) and are leads for deep dives, not findings. Benchmark scores are self-reported and unverified; per [[Evaluation Criteria]] they are not scored until we benchmark ourselves. Managed services are listed separately below. Full reviews are linked from [[Architecture Survey]].*

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
| 5 | [Hindsight](https://github.com/vectorize-io/hindsight) | 28.9k | 1.06M | 2026-09-25 | MIT | Fact, experience and observation networks + graph | **Deep dive** |
| 6 | [Graphiti](https://github.com/getzep/graphiti) | 31.2k | 610k | 2026-09-24 | Apache-2.0 | Temporal knowledge graph | **Surveyed:** [[Zep and Graphiti]] |
| 7 | [OpenViking](https://github.com/volcengine/OpenViking) | 38.7k | 441k | 2026-09-25 | AGPL-3.0 | File-based context database, tiered | Runner-up for a deep dive |
| 8 | [Supermemory](https://github.com/supermemoryai/supermemory) | 30.9k | 461k | 2026-09-23 | MIT | Extracted facts + graph; engine mostly hosted | Weak: core is closed |
| 9 | [Letta](https://github.com/letta-ai/letta-code) | 28.3k | 360k | 2026-09-25 | Apache-2.0 | Tiered / file-based | **Surveyed:** [[Letta]] |
| 10 | [Honcho](https://github.com/plastic-labs/honcho) | 7.3k | 767k | 2026-09-25 | AGPL-3.0 | Extracted facts about peers; per-observer views | **Deep dive** |
| 11 | [Semantic Kernel](https://github.com/microsoft/semantic-kernel) / Kernel Memory† | 28.6k / 2.2k | 285k | 2026-09-19 / 06-08 | MIT | Vector RAG | Skip (Kernel Memory dormant) |
| 12 | [LangMem](https://github.com/langchain-ai/langmem) | 1.7k | 700k | 2026-09-09 | MIT | Extracted facts over LangGraph's store | Weak: thin layer |
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
| 24 | [EverOS](https://github.com/EverMind-AI/EverOS) (was EverMemOS) | 13.2k | 21k | 2026-09-24 | Apache-2.0 | Memory cells → episodes and profiles | Runner-up for a deep dive |
| 25 | [txtai](https://github.com/neuml/txtai) | 13.0k | 13k | 2026-09-25 | Apache-2.0 | Vector + graph store | Weak: a store, not a memory system |
| 26 | [MemOS](https://github.com/MemTensor/MemOS) | 11.6k | ~1k | 2026-09-22 | Apache-2.0 | Tiered OS-style (MemCube) | Weak: heavy |
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

## Recommended deep dives

1. **Honcho.** Each participant (peer) keeps its own view of the others, e.g. "what B concluded about A". That is the closest built-in analogue to our participant labels. It runs on Postgres with pgvector, so filtering inside the search should be natural, and downloads are high. AGPL licence.
2. **Hindsight.** Second only to Mem0 in downloads among dedicated memory systems. Observations and opinions are consolidated from facts, which tests our union-inheritance rule. Its memory banks and tags look like hooks for labels.
3. **Cognee.** The only popular store with real per-dataset access control (read, write, share, and a separate database per dataset). It is the nearest existing permission layer to compare with our partitions.

**Runners-up:** OpenViking and EverOS.

## Managed services

*In progress.*

## Sources

- Metrics: GitHub REST API, [pypistats.org](https://pypistats.org) and the npm downloads API, all queried 2026-09-25.
- Discovery: [TeleAI-UAGI/Awesome-Agent-Memory](https://github.com/TeleAI-UAGI/Awesome-Agent-Memory).
