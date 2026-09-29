---
type: review
status: active
authority: reference
summary: "First selective-memory run (S1–S3, 3 worlds, 486 probes per system): memgate leaked 0 of 420 must-not probes with 66/66 recall; no-filter leaked 420/420; per-agent stores leaked 132/420, every one a witness recalling outside the location. Small and retrieval-level; recall is at ceiling."
created: 2026-09-29
updated: 2026-09-29
tags: [agentic-memory, benchmark, selective-memory, results]
---

# Review: selective memory S1–S3, 2026-09-29

*Snapshot of the first run of the [[Selective Memory Benchmark]]. Summary committed as benchmark/reports/selective-2026-09-29.json; probe-level data in benchmark/results/selective/sel-2026-09-29/ (gitignored). Worlds: benchmark/datasets/selective/world-{1,2,3}.json.*

**Result.** memgate on Hindsight leaked **0 of 420** probes that must not recall a code, and recalled **66 of 66** that should. The no-filter baseline leaked all 420, which shows the probes do detect leaks. Per-agent stores leaked 132: exactly the witness-elsewhere probes, a witness recalling outside the location. Scoping by agent alone misses the location dimension.

## Setup

- **Worlds:** 3 seeded worlds, each with 6 agents, 3 locations and 9 conversations (S1: four witness conversations; S2: {A,B}, {A,C}, {A,B,C}; S3: two shared facts, one retold with a newcomer present). Dialogue by gpt-oss-120b.
- **Probes:** every (agent, location, fact), 162 per world. A probe hits if the code appears in the top 20 recalled memories.
- **Answer key:** memgate's Cedar policies applied to ground truth.
- **Systems:** all on Hindsight 0.10.1, with gpt-oss-120b extraction and bge-small embeddings.

## Results

| Probe kind | Expected | No filter | Per-agent stores | memgate |
| --- | --- | --- | --- | --- |
| Witness, here | recall | 63/63 | 63/63 | **63/63** |
| Retold, to newcomer (S3) | recall | 3/3 | 3/3 | **3/3** |
| Witness, elsewhere | no recall | 132/132 leaked | 132/132 leaked | **0/132** |
| Non-witness | no recall | 279/279 leaked | 0/279 | **0/279** |
| Untold, to newcomer (S3) | no recall | 9/9 leaked | 0/9 | **0/9** |
| **Overall leak rate** | | **100%** | **31.4%** | **0%** |
| **Overall recall** | | 100% | 100% | **100%** |

By scenario, memgate leaked 0/186 in S1, 0/141 in S2 and 0/93 in S3, with full recall in each.

## What it does and doesn't show

- **It shows:** labels are enforced inside Hindsight's search, including for the facts and observations Hindsight derives in the background. Across your {A,B}/{A,C}/{A,B,C} case and retelling, nothing crossed a label set, and nothing permitted was lost.
- **Recall is at ceiling.** With 9 conversations per world and k = 20, the right memory is always retrieved. Recall only becomes a meaningful measure with bigger worlds.
- **Retrieval level only.** A paraphrased leak (content without its code) isn't detected. Answer-level checks with a judge come later.
- **Small:** 486 probes per system, one run. Differences near zero need larger worlds and repeated seeds before they mean much.

## Next

- Scale the worlds up (more conversations and agents, recall below ceiling).
- An answer-level check with a judge.
- Suites S4 (environments and carry-out) and S5 (high assurance), then S6 (hierarchy trap) and S7 (scale).
- A second adapter (Mem0) to show the strategy is portable.
