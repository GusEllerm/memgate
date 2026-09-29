---
type: module
status: active
authority: describes
summary: "The selective-memory benchmark (suites S1–S3): seeded worlds with planted codes in LLM-written dialogue, a Cedar answer key independent of the systems, and three systems on Hindsight (no filter, per-agent stores, memgate). Measures leak rate and recall per probe kind and scenario."
created: 2026-09-29
updated: 2026-09-29
tags: [module, benchmark, selective-memory]
---

# Selective Memory Benchmark

> [!abstract] Role
> The deciding benchmark in [[Benchmark Plan]]. It asks whether a memory system keeps context-locked memories locked, and still recalls what an agent is allowed to. This first version covers suites S1–S3.

## Pieces

- **Worlds** (`benchmark/src/smbench/selective/world.py`). `plan` builds a seeded `World`: 6 agents, 3 locations, and 9 `Conversation` records, each stating one or two `Fact` codes (the canaries).
  - **S1 (witness):** four pair or trio conversations in random locations.
  - **S2 (triad):** {A,B}, then {A,C}, then {A,B,C}, all in one location.
  - **S3 (retelling):** A and B share two facts. Later, with newcomer X present, A retells one of them.
- **Dialogue** (`benchmark/src/smbench/selective/dialogue.py`). `write_dialogue` has gpt-oss-120b write each conversation. It retries until every code stated is present verbatim, no other code appears, and only participants speak.
  - `build` saves each world to benchmark/datasets/selective/world-<seed>.json, the **released dataset**, committed. Saved worlds are never regenerated.
- **Answer key** (`benchmark/src/smbench/selective/oracle.py`). `expected` applies memgate's Cedar policies to the ground truth: the label sets of the conversations each fact was stated in. It decides whether each (agent, location, fact) should recall, independently of every system.
  - `probe_kind` classifies each probe: witness-here, witness-elsewhere, non-witness, retold-to-newcomer, or untold-to-newcomer.
- **Systems** (`benchmark/src/smbench/selective/systems.py`), all on Hindsight 0.10.1, so the permission strategy is the only difference:
  - `NoFilter`: one bank per world, recall unfiltered. The leak baseline.
  - `PerAgent`: one bank per agent, holding what it witnessed. It ignores location.
  - `Memgate`: memgate's Hindsight client against a gated Hindsight (port 8890, its own world, registry and database).
- **Runner** (`benchmark/src/smbench/selective/run.py`). It ingests every conversation, waits for background processing, then probes every (agent, location, fact) with "What is <topic>?". A probe **hits** if the fact's code appears in the top 20 recalled memories. `summarise` reports leak rate (hits on must-not probes) and recall (hits on should probes), overall, by probe kind and by scenario.

## Limits of this version

- **Retrieval-level only.** Paraphrased leaks, where the content surfaces without the code, aren't caught. An answer-level check with a judge comes later.
- **Small scale:** 3 worlds × 162 probes. Suites S4–S7 (environments, high assurance, hierarchy, scale) are still to come.
