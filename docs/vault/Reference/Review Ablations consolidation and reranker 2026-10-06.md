---
type: review
status: active
authority: reference
summary: "Two ablations on the selective benchmark's env worlds, run for the 2026-10-06 rulings. Consolidation: memgate with Hindsight's observations off matched or beat a fresh observations-on control under every question style (indirect at 5: 96% off, 85% on), so nameless class sets go in a bank with observations off at no recall cost. Reranker: without Hindsight's cross-encoder (RRF passthrough) recall collapses on hard questions (indirect at 20: 50% against 95%), so a torch-free server must keep a reranker; flashrank (ONNX, no torch) holds within two points of the local one, so `--embeddings-provider onnx --reranker flashrank` is the slim configuration."
created: 2026-10-06
updated: 2026-10-06
tags: [memgate, benchmark, selective-memory, ablation, results]
---

# Review: consolidation and reranker ablations, 2026-10-06

*Run from the 0.6.0 worktree with the [[Selective Memory Benchmark]] harness (`--bank-config` added for the first, a Hindsight with `HINDSIGHT_API_RERANKER_PROVIDER` changed for the second), on the env worlds 21–23 (S4–S5: 1,620 probes per style, multi 762), every question style from [[Review Selective harder probes 2026-10-01]]. Both answer questions in the [[Decision Log]] rows of 2026-10-06. Results in benchmark/results/selective/sel-env-{noobs,obs,rrf,flashrank}-*-2026-10-06 (gitignored).*

## 1. Consolidation off for memgate's sets

The question: does keeping a class of personal memory out of Hindsight's consolidation (no observations) cost recall? memgate on Hindsight, the env worlds ingested twice on the same day: once into banks with `enable_observations` and `enable_auto_consolidation` off, once with them on (a fresh control, since extraction varies between runs).

| Style | Observations off: leak, recall at 20, at 5 | Observations on (fresh control) | On, the 2026-09-30 banks |
| --- | --- | --- | --- |
| direct | 0/1,446; 100%; **100%** | 0/1,446; 100%; 100% | 0; 100%; 100% |
| paraphrase | 0/1,446; 100%; **100%** | 0/1,446; 100%; 99.4% | 0; 100%; 100% |
| indirect | 0/1,446; 100%; **96.0%** | 0/1,446; 98.9%; 84.5% | 0; 100%; 89.1% |
| multi | 0/478; 100%; **99.7%** | 0/478; 100%; 93.7% | 0; 100%; 98.9% |

**Reading it.** Observations never helped here and cost a little at 5 under vague questions: the derived observation and its source fact compete for the top ranks, and the observation's rewording matches an indirect question less often than the fact does. On short, self-contained items (what a carry-out is), consolidation has nothing to merge. So the ruling's measurement comes out one way: **nameless class sets go in a bank of their own with observations off**, with no recall cost on these worlds; 0.6.0 does this for any class the world file marks `consolidate: false`. Caveat: a class whose items repeat or contradict each other over months might benefit from consolidation's updates; these worlds don't test that.

## 2. The reranker's worth (for a torch-free server)

The question: torch is 550 MB of the 1.8 GB server environment and is needed only by Hindsight's local cross-encoder reranker (and the local embedder, which has an ONNX alternative). What does recall lose without the cross-encoder? Unfiltered Hindsight (the no-filter baseline), env worlds, embeddings unchanged.

| Style | Local cross-encoder (the 2026-09-29/10-01 runs): at 20, at 5 | RRF passthrough (no reranking) | flashrank (ONNX, no torch) |
| --- | --- | --- | --- |
| direct | 100%; 100% | 100%; 100% | 100%; 100% |
| paraphrase | 100%; 96.5% | 98.9%; 89.7% | 100%; 96.5% |
| indirect | 94.8%; 66.1% | **50.0%; 29.9%** | **92.5%; 67.2%** |
| multi | 100%; 78.2% | 99.3%; 51.1% | 98.6%; 78.5% |

**Reading it.** Retrieval order alone (RRF over the semantic, keyword and graph channels) is fine for questions that name the topic and collapses on indirect ones: half the facts fall out of the top 20. A torch-free server therefore needs a reranker that runs without torch, and **flashrank (an ONNX cross-encoder, no torch) holds within two points of the local one on every style**: indirect at 20 92.5% against 94.8%, at 5 67.2% against 66.1%. So `memgate serve --embeddings-provider onnx --reranker flashrank` (0.6.0) is the torch-free configuration to recommend; `--reranker rrf` exists for latency-bound deployments that accept the loss. Caveat: one env-world run per configuration, and the no-filter system; the slim configuration should be re-measured once with memgate's filter and the onnx embedder together before a deployment switches to it.
