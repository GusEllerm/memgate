---
type: module
status: active
authority: describes
summary: "The selective-memory benchmark (suites S1–S5): seeded worlds with planted codes in LLM-written dialogue, a Cedar answer key independent of the systems, and three systems on Hindsight (no filter, per-agent stores, memgate). Measures leak rate and recall per probe kind and scenario."
created: 2026-09-29
updated: 2026-09-30
tags: [module, benchmark, selective-memory]
---

# Selective Memory Benchmark

> [!abstract] Role
> The deciding benchmark in [[Benchmark Plan]]. It asks whether a memory system keeps context-locked memories locked, and still recalls what an agent is allowed to. It covers suites S1–S5.

## Pieces

- **Worlds** (`benchmark/src/smbench/selective/world.py`). `plan` builds a seeded `World` of `Conversation` records, each stating one or two `Fact` codes (the canaries). Sizes are set in `SIZES`:
  - **small:** 6 agents, 3 locations, 9 conversations (1 triad, 1 retelling), 162 probes.
  - **large:** 12 agents, 5 locations, 51 conversations (36 witness, 3 triads, 3 retellings), about 3,060 probes. Large worlds build topics from shared patterns (`PATTERNS` × `OBJECTS`, e.g. "the combination for the seminar room"), so many facts look alike.
  - **env** (`plan_env`): S4 and S5. Three environments: campus (open: lab, cafe, and the high-assurance vault), studio (selective, opinions and skills only: gallery), and severed-floor (*Severance*: macrodata). Each `Fact` is a fact or an opinion. Two rounds per world:
    - **S4:** a pair talks in the lab, the gallery and the macrodata room (a fact and an opinion each); afterwards one of them tries to carry both into personal memory.
    - **S5:** a pair talks in the vault; one tries to carry the opinion out; the other keeps a personal note in the vault.
    - About 540 probes per world.
  - **S1 (witness):** four pair or trio conversations in random locations.
  - **S2 (triad):** {A,B}, then {A,C}, then {A,B,C}, all in one location.
  - **S3 (retelling):** A and B share two facts. Later, with newcomer X present, A retells one of them.
- **Dialogue** (`benchmark/src/smbench/selective/dialogue.py`). `write_dialogue` has gpt-oss-120b write each conversation. It retries until every code stated is present verbatim, no other code appears, and only participants speak.
  - `build` writes dialogue six conversations at a time and saves each world to benchmark/datasets/selective/ (world-<seed>.json, world-<seed>-large.json), the **released dataset**, committed. Saved worlds are never regenerated.
- **Answer key** (`benchmark/src/smbench/selective/oracle.py`). `expected` applies memgate's Cedar policies to the ground truth: the label sets of the conversations each fact was stated in. It decides whether each (agent, location, fact) should recall, independently of every system.
  - **S4/S5:** `permitted_carry_outs` asks memgate's `Policy.may_carry_out` whether each carry-out attempt is allowed (from the conversation's location); only permitted carry-outs, and notes (readable in their own location only), count as holding a fact.
  - `probe_kind` classifies each probe: witness-here, witness-elsewhere, non-witness, retold-to-newcomer, untold-to-newcomer, carried-fact or carried-opinion, carry-refused-fact, carry-refused-opinion or carry-refused-ha, ha-witness-inside, ha-witness-outside, note-here, note-elsewhere, note-other-agent. It is written independently of the answer key, so the two cross-check each other.
- **Systems** (`benchmark/src/smbench/selective/systems.py`), all on Hindsight 0.10.1, so the permission strategy is the only difference:
  - `NoFilter`: one bank per world, recall unfiltered. The leak baseline.
  - `PerAgent`: one bank per agent, holding what it witnessed. It ignores location.
  - `Memgate`: memgate's Hindsight client against a gated Hindsight (port 8890, its own world, registry and database).
  - **Carry-outs and notes:** the baselines have no permission check, so they store every attempted carry-out (`personal_text`) and note (`note_text`). memgate goes through carry-out and keep-note, so refused carry-outs are never stored.
- **Runner** (`benchmark/src/smbench/selective/run.py`).
  - **Ingest:** runs each system's jobs several at a time (--ingest-workers, default 4; the gateway still caps ALCF at 6), then waits for background processing.
  - **Probe:** asks every (agent, location, fact) "What is <topic>?". A probe records the rank at which the code first appears in the top 20 recalled memories.
  - **Score:** `summarise` reports leak rate (hits in the top 20 on must-not probes), plus recall at 20 and at 5 (should probes), overall, by probe kind and by scenario.
  - **Side-effect audit** (S5): recalls made inside a high-assurance location run first, bracketed by a snapshot of each system's banks (for memgate, the shared bank and every high-assurance partition) (`snapshot`: node, link, document and observation counts, last write, operation count). Any change is reported in side_effects.json.

## Limits of this version

- **Probes are retrieval-level.** A probe counts a leak only when the exact code is recalled. `benchmark/src/smbench/selective/leakcheck.py` looks further, in two ways:
  - `lineage` (exact, no LLM): in every memgate bank, each memory unit must carry its document's label set, and each consolidated observation the label set of every memory it was built from.
  - `Checker` (answer level): re-asks must-not probes as the agent, requesting everything Hindsight's recall can return (entity observations, raw chunks, source facts, trace). It scans the whole response for the code, has gpt-oss-120b answer from it, and has the judge label the answer VALUE, HINT or NONE. A sample of per-agent leaks is the positive control.
- **Scale:** small worlds give 3 × 162 probes, large worlds about 3,060 each. env worlds 3 × 540. Suites S6–S7 (hierarchy, scale) are still to come. Results: [[Review Selective S1-S3 2026-09-29]], [[Review Selective large 2026-09-29]], [[Review Selective S4-S5 2026-09-29]].
- **Refusal count:** the runner prints memgate's refused carry-outs per world after probing (a running total before 2026-09-30), so `--skip-ingest` runs don't report it.
