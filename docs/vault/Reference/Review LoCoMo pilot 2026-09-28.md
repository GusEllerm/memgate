---
type: review
status: active
authority: reference
summary: "LoCoMo pilot on conv-26 (152 questions), gpt-oss-120b answering, Nemotron 3 Ultra judging, k=20: Hindsight 70.4%, Mem0 61.2% (paired p≈0.04, one conversation). Full LoCoMo for both systems is about 2–3.5 hours of wall time under the 6-request cap."
created: 2026-09-28
updated: 2026-09-28
tags: [memgate, benchmark, locomo, results]
---

# Review: LoCoMo pilot, 2026-09-28

*Snapshot of a pilot run with the [[LoCoMo Harness]] through the [[ALCF Gateway]], per [[Benchmark Plan]]. The raw run data is in benchmark/results/ (gitignored); the summary is committed as benchmark/reports/locomo-pilot-2026-09-28.json.*

**Result.** On one conversation, Hindsight answered 70.4% of questions correctly and Mem0 61.2%. The gap is significant in a paired test (27 questions only Hindsight got right, 13 only Mem0; exact McNemar p≈0.04). But it rests on one conversation of ten. Both runs completed with no failed requests, and throughput is fine for a full run.

## Setup

| | Value |
| --- | --- |
| Data | LoCoMo conv-26: 19 sessions, 419 turns, 152 questions (adversarial category excluded) |
| Answer and memory-system model | openai/gpt-oss-120b (ALCF Sophia) |
| Judge | nemotron-3-ultra (ALCF Minerva), with retry on empty replies |
| Embedder | BAAI/bge-small-en-v1.5, local, both systems |
| Retrieval depth | k = 20 memories per question |
| Systems | hindsight-api 0.10.1; mem0ai 2.2.0 (open source, with the max_tokens and session-date fixes in [[LoCoMo Harness]]) |
| Load | Both systems ran at once, sharing the gateway's 6-request cap |

## Scores (judge accuracy, 95% Wilson interval)

| Category | n | Hindsight | Mem0 |
| --- | --- | --- | --- |
| **Overall** | 152 | **70.4%** (62.7–77.1) | **61.2%** (53.3–68.6) |
| Single-hop | 70 | 77.1% | 62.9% |
| Temporal | 37 | 78.4% | 70.3% |
| Multi-hop | 32 | 40.6% | 43.8% |
| Open-domain | 13 | 84.6% | 69.2% |
| Token F1 (overall) | 152 | 0.391 | 0.327 |

**Against published claims.** Both are well below the vendors' figures (Hindsight about 92% on LoCoMo, Mem0 92.5%). That is expected rather than alarming:
- we use one open model for both memory and answering;
- one fixed answer prompt, with no system-specific answering pipeline;
- one conversation.

This is exactly why the plan holds everything fixed. Our numbers compare systems with each other, not with vendor claims.

## Throughput and cost

| | Hindsight | Mem0 |
| --- | --- | --- |
| Ingest (19 sessions, sequential) | 447 s (23.5 s per session) | 468 s (24.6 s per session) |
| Wait for background processing | 60 s | 0 s |
| 152 questions (6 in parallel) | 195 s | 186 s |
| Median search / answer / judge | 0.63 / 3.1 / 0.9 s | 0.01 / 3.8 / 2.0 s |

- **Gateway:** 741 requests, 0 failed, 5 retried. Concurrency peaked at the cap of 6; the longest queue wait was 33 s.
- **Tokens:** the memory systems' own calls used 806k prompt and 214k completion tokens for both systems together (not split per system, because their internal calls carry no labels). Answering and judging used about 185k prompt and 60k completion tokens per system.
- **Projection for all 10 conversations** (5,782 turns, 1,540 questions):
  - Per system: ingest about 1.7 h if sessions are loaded one at a time, and questions about 30 min.
  - Loading about three conversations in parallel per system would fill the 6 slots and bring **both systems to roughly 2 hours of wall time**, or about 3.5 hours without that parallelism.
  - Memory-system tokens: about 11M prompt and 3M completion for both systems.

## Issues found and fixed during setup

1. **Mem0 silently stored nothing.** Its default max_tokens of 2000 cut gpt-oss-120b's extraction off mid-JSON (reasoning tokens count toward the limit). Raised to 8000.
2. **Mem0 dated memories to today.** The open-source add() anchored relative dates to the wall clock ("yesterday" in May 2023 became 27 September 2026). Fixed by giving extraction the session date, as the Platform's timestamp does.
3. **The Hindsight client** runs its own event loop, so there is one client per worker thread.
4. **The judge returned an empty reply twice.** Added retries, a larger token budget, and a re-grade mode.

## Next

- **Full LoCoMo** for both systems, loading conversations in parallel.
- **Falda** adapter.
- **Split internal token use per system:** label the memory systems' own calls, e.g. by giving each system its own gateway path.
- **Judge calibration:** about 200 items, Ultra against Super, with a Claude spot-check.
