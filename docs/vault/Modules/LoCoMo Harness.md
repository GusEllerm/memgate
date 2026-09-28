---
type: module
status: active
authority: describes
summary: "Runs LoCoMo against one memory system through a common adapter: ingest sessions, wait for background processing, retrieve k memories per question, answer with gpt-oss-120b, grade with Nemotron 3 Ultra, and score judge accuracy and F1 per category."
created: 2026-09-28
updated: 2026-09-28
tags: [module, benchmark, locomo]
---

# LoCoMo Harness

> [!abstract] Role
> Efficacy runs where the memory system is the only thing that varies: same transcripts, same embedder, same retrieval depth, same answer prompt, same judge.

Code: `benchmark/src/smbench/locomo/run.py`, with `benchmark/src/smbench/locomo/data.py`, `benchmark/src/smbench/locomo/prompts.py` and `benchmark/src/smbench/locomo/metrics.py`. Adapters live in `benchmark/src/smbench/adapters/`. Plan in [[Benchmark Plan]]; all LLM traffic goes through the [[ALCF Gateway]].

## How a run works

1. **Load.** `load` reads LoCoMo (CC BY-NC 4.0, downloaded and hash-checked by `benchmark/scripts/get_locomo.sh`, never committed).
   - `sessions` turns each conversation into dated sessions, adding image captions to turns that share an image.
   - `questions` drops category 5 (adversarial) by convention, leaving 1,540 of 1,986 questions.
2. **Ingest.** `Runner.ingest` gives every session to the adapter's `ingest_session`, then calls `finalize`, which waits for background extraction and consolidation. Progress goes to state.json, so a run resumes where it stopped.
3. **Answer and grade.** `Runner.questions` runs six questions in parallel; the gateway still caps ALCF at 6. For each question it:
   - retrieves k = 20 memories;
   - answers with the shared `ANSWER` prompt on gpt-oss-120b;
   - grades with the `JUDGE` prompt on nemotron-3-ultra;
   - appends one line to answers.jsonl.
4. **Score.** `summarise` reports judge accuracy (primary) and token `f1`, overall and per category (`CATEGORIES`: multi-hop, temporal, open-domain, single-hop). The run's settings and timings are saved in summary.json.

## Adapters

`MemoryAdapter` is the protocol: `ingest_session`, `finalize`, `search`, `describe`. `load_adapter` picks the system. Both use `EMBEDDER` (BAAI/bge-small-en-v1.5).

| Adapter | Setup and decisions |
| --- | --- |
| `HindsightAdapter` | Talks to hindsight-api 0.10.1 started by `benchmark/scripts/serve_hindsight.sh`. LLM via the gateway; LLM trace and OTel off. Setup: one bank per conversation; one synchronous retain per session transcript with its timestamp; `finalize` polls the bank's operations until none are pending; recall with budget "mid", first k results. The client runs its own event loop, so there is one client per worker thread |
| `Mem0Adapter` | mem0ai 2.2.0 in-process with local Qdrant, fastembed and telemetry off. One add per session, speaker A as user and B as assistant, names kept in the text. Two fixes, both needed for a fair run: **max_tokens raised to 8000**, because Mem0's 2000 cut gpt-oss-120b's extraction off mid-JSON and silently stored nothing; and **extraction dated to the session** via `_resolve_session_dates`, because the OSS add() anchors "yesterday" to today's wall clock (the Platform's timestamp does the same job) |

Each system runs in its own virtual environment (benchmark/.venvs/, gitignored), with smbench installed into it.
