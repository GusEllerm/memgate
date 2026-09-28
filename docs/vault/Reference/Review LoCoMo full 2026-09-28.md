---
type: review
status: active
authority: reference
summary: "Full LoCoMo (10 conversations, 1,540 questions), gpt-oss-120b answering, Nemotron 3 Ultra judging, k=20: Hindsight 69.5% and Mem0 69.4%, statistically indistinguishable (paired p=0.96). The pilot's 9-point gap was one-conversation noise. 1 h 50 min wall time, ~10k requests, none failed."
created: 2026-09-28
updated: 2026-09-28
tags: [agentic-memory, benchmark, locomo, results]
---

# Review: full LoCoMo, 2026-09-28

*Snapshot of the full run with the [[LoCoMo Harness]] through the [[ALCF Gateway]], following [[Review LoCoMo pilot 2026-09-28]]. Summary committed as benchmark/reports/locomo-full-2026-09-28.json; raw data in benchmark/results/ (gitignored).*

**Result.** With the model, embedder, retrieval depth, answer prompt and judge held fixed, **Hindsight and Mem0 are tied on LoCoMo**. Over 1,540 questions, Hindsight scored 69.5% and Mem0 69.4%. Of the questions they disagreed on, 162 went to Hindsight and 160 to Mem0 (exact McNemar p=0.96). The 9-point gap in the one-conversation pilot was noise. So efficacy does not separate these two systems. The choice between them should rest on the selective-memory properties this project needs ([[Hindsight]], [[Mem0]]).

## Setup

As in the pilot:
- gpt-oss-120b (ALCF Sophia) for the memory systems and answering;
- nemotron-3-ultra (ALCF Minerva) as judge;
- BAAI/bge-small-en-v1.5 embeddings;
- k = 20 memories per question;
- hindsight-api 0.10.1 and mem0ai 2.2.0;
- the adversarial category excluded.

Per system, three conversations ran in parallel, one process each; both systems ran at the same time under the gateway's cap of 6.

## Scores (judge accuracy, 95% Wilson interval)

| Category | n | Hindsight | Mem0 |
| --- | --- | --- | --- |
| **Overall** | 1,540 | **69.5%** (67.1–71.7) | **69.4%** (67.0–71.6) |
| Single-hop | 841 | 75.7% (72.7–78.5) | 76.3% (73.4–79.1) |
| Temporal | 321 | 74.5% (69.4–78.9) | 77.0% (72.0–81.2) |
| Multi-hop | 282 | 49.6% (43.9–55.5) | 45.0% (39.3–50.9) |
| Open-domain | 96 | 56.3% (46.3–65.7) | 54.2% (44.2–63.8) |
| Token F1 | 1,540 | 0.442 | 0.420 |

Per conversation, Hindsight ranges from 60.5% to 75.3% and Mem0 from 65.3% to 76.3%. Neither system wins consistently.

## Checks on the result

- **Consolidation timing didn't matter.** Hindsight's first pass started answering some conversations before background consolidation had finished (an adapter bug, fixed; see [[LoCoMo Harness]]). Only the question phase was re-run. On the 1,382 questions both passes answered, the early pass scored 69.5% and the corrected one 69.4% (p=1.0). The table uses the corrected pass.
- **Runs vary by several points.** conv-26 was run twice per system:
  - Hindsight: 70.4% in the pilot, 67.1% here (p=0.51);
  - Mem0: 61.2%, then 67.1% (p=0.14).

  So ±5 points on a single conversation is within noise. Claims need all 1,540 questions, and ideally repeated runs.

## Cost and throughput

- **Wall time:** 1 h 50 min (11:15–13:05), including Hindsight's question re-run. Without it, about 1.5 h.
- **Gateway:** 9,991 requests, **0 failed, 0 retried**. Concurrency stayed at the cap of 6 throughout; the longest queue wait was 51 s.
- **Tokens:**
  - The memory systems' own calls: 10.1M prompt and 2.6M completion for both systems together. The pilot projected 11M and 3M.
  - Answers and judging: about 1.5M prompt and 0.35M completion of gpt-oss-120b per pass, plus about 0.23M prompt and 0.31M completion of Nemotron Ultra.
- **Per-process time totals:**
  - ingest: Hindsight 9,572 s, Mem0 9,006 s, summed over conversation processes;
  - questions: Hindsight 2,425 s, Mem0 6,310 s.

  These overlapped in time and competed for the same 6 slots, so they are not a clean speed comparison. The speed benchmark in [[Benchmark Plan]] measures that properly.

## What this means

- **On standard long-conversation recall,** with the model held fixed, Hindsight and Mem0 are equivalent. Efficacy gives neither an advantage. Our earlier preference for Hindsight rests on how well it fits selective memory, where it needs no core changes. Mem0 needs its add-time lookup fixed, and has no lineage.
- **LoCoMo can't separate these systems at this model scale.** The selective-memory benchmark is where the real differences should show up.

## Next

- **Falda adapter,** to complete the shortlist.
- **Judge calibration:** about 200 items, Ultra against Super, with a Claude spot-check.
- **Split the memory systems' own tokens per system:** label them per system in the gateway.
- **A second full run,** to estimate run-to-run variance across all 1,540 questions.
