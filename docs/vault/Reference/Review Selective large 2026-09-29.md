---
type: review
status: active
authority: reference
summary: "Selective memory S1–S3 on two large worlds (12 agents, 5 locations, 51 conversations with look-alike topics; 6,120 probes per system): memgate leaked 0 of 5,891 with recall 99.1% at 20 and at 5; no filter leaked 99%; per-agent stores leaked every witness-elsewhere probe. Every missed recall was a Hindsight extraction loss, not filtering. Recall is still near ceiling because queries name the topic."
created: 2026-09-29
updated: 2026-09-29
tags: [memgate, benchmark, selective-memory, results]
---

# Review: selective memory, large worlds, 2026-09-29

*Snapshot of the [[Selective Memory Benchmark]] on its large size, following [[Review Selective S1-S3 2026-09-29]]. Summary committed as benchmark/reports/selective-large-2026-09-29.json; worlds in benchmark/datasets/selective/world-{11,12}-large.json. Wall time about 1 h 45 min.*

**Result.** memgate leaked **0 of 5,891** must-not probes. Recall was **227/229 (99.1%)** at both k = 20 and k = 5. No filter leaked 99% and per-agent stores 15.4% (every witness-elsewhere probe). All three systems missed 2 of 229 should-recall probes. Each miss was a fact whose code Hindsight's extraction dropped for that system's copy of the conversation, not a filtering error.

## Results

| Probe kind | Expected | No filter | Per-agent stores | memgate |
| --- | --- | --- | --- | --- |
| Witness, here | recall | 221/223 (97.3% at 5) | 221/223 (99.1% at 5) | **221/223 (99.1% at 5)** |
| Retold, to newcomer (S3) | recall | 6/6 | 6/6 | **6/6** |
| Witness, elsewhere | no recall | 908/916 leaked | 908/916 leaked | **0/916** |
| Non-witness | no recall | 4,895/4,945 leaked | 0/4,945 | **0/4,945** |
| Untold, to newcomer (S3) | no recall | 30/30 leaked | 0/30 | **0/30** |
| **Leak rate** | | 99.0% | 15.4% | **0.0%** |
| **Recall at 20 / at 5** | | 99.1% / 97.4% | 99.1% / 99.1% | **99.1% / 99.1%** |

By scenario, memgate leaked 0/4,163 (S1), 0/1,038 (S2) and 0/690 (S3).

**No filter's "non-leaks"** (58 of 5,891) all involve one fact its copy of the conversation never extracted. The per-agent stores' missed recalls are two other facts. Extraction varies from run to run, and each system stored its own copy.

## Reading it

- **Zero leaks at 12× the scale,** across 51 conversations per world with look-alike topics and background consolidation. The filter holds.
- **Filtering doesn't cost recall here, and slightly helps precision.** memgate recall at 5 is 99.1%, against 97.4% for no filter, whose top 5 is crowded by look-alike facts the agent shouldn't see.
- **Recall is still near ceiling.** Each probe names the fact's topic ("What is the combination for the seminar room?"), so retrieval is easy even among look-alikes. **To measure a recall cost,** probes need to be indirect or paraphrased ("What did Bo say about the room booked for Friday?"), or worlds need to be much larger.
- **Leaks are still checked at retrieval level only** (exact code). Paraphrased leaks need an answer-level check.

## Next

- Harder probes: indirect and paraphrased questions, and multi-fact questions.
- An answer-level leak check, on a targeted sample.
- Suites S4 (environments and carry-out) and S5 (high assurance).
