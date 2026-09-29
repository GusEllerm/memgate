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
| Multi-hop | 282 | 49.7% (43.9–55.5) | 45.0% (39.3–50.9) |
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

## Against published results

**Category labels differ across papers.** The Mem0 and Hindsight papers call category 1 "single-hop" and category 4 "open-domain". Their overall scores only add up that way. The data says the reverse: category 1 averages 3.1 evidence turns (98% need more than one), and category 4 averages 1.07. So per-category scores below are aligned by **category number**, using our semantic names.

| Source | Memory setup | Answer / judge | Overall | Multi-hop (1) | Temporal (2) | Open-domain (3) | Single-hop (4) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **Ours, Mem0** | OSS 2.2.0, k=20 | gpt-oss-120b / Nemotron Ultra | **69.4** | 45.0 | 77.0 | 54.2 | 76.3 |
| **Ours, Hindsight** | 0.10.1, recall, k=20 | gpt-oss-120b / Nemotron Ultra | **69.5** | 49.7 | 74.5 | 56.3 | 75.7 |
| [Mem0 paper](https://arxiv.org/abs/2504.19413) (2025), Mem0 | OSS (then), top-k memories | GPT-4o-mini / stronger LLM, 10 runs | 66.9 | 67.1 | 55.5 | 51.2 | 72.9 |
| [Hindsight paper](https://arxiv.org/abs/2512.12818), Hindsight | recall, budget high, 4,096 fact tokens + 8,192 raw-transcript tokens | **gpt-oss-120b** / gpt-oss-120b, lenient prompt | 85.7 | 76.8 | 79.4 | 62.5 | 93.7 |
| [Mem0 docs](https://docs.mem0.ai/core-concepts/memory-evaluation) (current) | **Platform** v3, top-200 (~7k tokens per query) | not stated | 92.5 | – | – | – | – |
| [Hindsight benchmarks site](https://benchmarks.hindsight.vectorize.io/) | not stated | not stated | 92 | – | – | – | – |

Other points of reference, all self-reported:
- **Memobase:** 75.78.
- **Zep's own rerun:** 75.14 (GPT-4o).
- **LangMem:** 58.10, and **OpenAI memory:** 52.90, both as measured in the Mem0 paper.

**Independent check.** [Maximem](https://www.maximem.ai/blog/state-of-ai-memory-2026-claimed-vs-observed), which sells a competing product (disclosed), reran Mem0 on LongMemEval with GPT-5 answering and a strict binary judge. It measured 57.5%, then 73.8% after an update, against a claimed 93.4%. It attributes the gap to benchmark-specific prompting.

**Reading it.**
- **Our Mem0 matches its paper.** 69.4% against 66.9% with GPT-4o-mini: the harness is sound. Our temporal score is much higher (77.0 vs 55.5), plausibly thanks to the session-date fix and a reasoning model, and our multi-hop score lower (45.0 vs 67.1).
- **Our Hindsight trails its paper by 16 points on the same backbone** (69.5% vs 85.7% with gpt-oss-120b). An investigation on 2026-09-29 read Hindsight's paper-era evaluation code (vectorize-io/hindsight @ fa554b89) and **found no bug in our pipeline**. The gap is protocol:
  1. **The judge prompt.** Theirs marks an answer correct "as long as it touches on the same topic". Ours asks for the same thing.
  2. **Retrieval volume.** They recall with budget high, 4,096 tokens of facts, **plus 8,192 tokens of raw transcript and 2,048 of entities**. We take 20 memories, about 700 tokens.
  3. **The answer step.** They ask for "say them all", with high reasoning effort and no length cap. We use a 10-word cap.
  4. **Denominator.** They drop errored questions.

  **Correction:** the paper answered via recall, not reflect. Their own reflect run scored lower (77.24% vs 79.61%).

  In about two-thirds of our Hindsight misses, the evidence was at least partly retrieved (62% had half or more of the gold's content). So answering and grading dominate the gap. By eye, about 4 in 30 wrong answers were judge errors on our side (e.g. "January 1, 2022" vs gold "2022").

  **Minor issues found:**
  - year-only facts render as [YYYY-01-01];
  - observations and the facts they came from both appear in the 20 slots, about 12% near-duplicates. Fix with types=["world","experience"] or prefer_observations.

  **Re-grades, 2026-09-29:** all 3,080 existing answers were re-graded with gpt-oss-120b as judge. No re-answering.

  | Judge model / prompt | Hindsight | Mem0 | Agreement with original |
  | --- | --- | --- | --- |
  | nemotron-3-ultra / ours (original) | 69.5% | 69.4% | – |
  | gpt-oss-120b / ours | 69.8% | 69.4% | ~95% |
  | gpt-oss-120b / **Hindsight's lenient prompt** | **76.9%** | **76.4%** | ~91% |

  **The judge model doesn't matter; the judge prompt is worth about 7 points,** equally for both systems. The rest of the gap (~9 points to 85.7%) is the paper's larger retrieval budget (facts plus raw transcript) and its answer prompt. Under every judge, Hindsight and Mem0 stay tied.
- **Headline numbers of 92% or more** (Mem0 Platform v3, Hindsight's site) use the vendor's own pipeline, large retrieval budgets and unstated models. They aren't comparable to a fixed-protocol run.
- **What would attribute the gaps:** a small ablation on one or two conversations:
  - Hindsight answering via reflect;
  - both systems at a ~7k-token retrieval budget instead of k=20;
  - our answers re-graded with gpt-oss-120b as judge.

## What this means

- **On standard long-conversation recall,** with the model held fixed, Hindsight and Mem0 are equivalent. Efficacy gives neither an advantage. Our earlier preference for Hindsight rests on how well it fits selective memory, where it needs no core changes. Mem0 needs its add-time lookup fixed, and has no lineage.
- **LoCoMo can't separate these systems at this model scale.** The selective-memory benchmark is where the real differences should show up.

## Next

- **Falda adapter,** to complete the shortlist.
- **Judge calibration:** about 200 items, Ultra against Super, with a Claude spot-check.
- **Split the memory systems' own tokens per system:** label them per system in the gateway.
- **A second full run,** to estimate run-to-run variance across all 1,540 questions.
