---
type: review
status: active
authority: reference
summary: "Selective memory S4 (environments and carry-out) and S5 (high assurance) on three env worlds (1,620 probes per system): memgate leaked 0 of 1,446 with recall 174/174 at 20 and at 5; it refused exactly the 24 carry-outs the answer key forbids, and stored exactly what the key expects. No filter leaked 100%; per-agent stores leaked 23.2%, including every high-assurance fact asked about outside the vault. High-assurance recalls changed no bank for any system."
created: 2026-09-29
updated: 2026-09-30
tags: [agentic-memory, benchmark, selective-memory, results, high-assurance]
---

# Review: selective memory S4 and S5, 2026-09-29

*Snapshot of the [[Selective Memory Benchmark]] on its env size, following [[Review Selective large 2026-09-29]]. Summary and audit committed as benchmark/reports/selective-env-2026-09-29.json; worlds in benchmark/datasets/selective/world-{21,22,23}-env.json. Ingestion about 24 min; probing 4 min.*

**Result.** memgate leaked **0 of 1,446** must-not probes, with recall **174/174** at both k = 20 and k = 5. No filter leaked all 1,446. Per-agent stores leaked 336 (23.2%): every carry-out that should have been refused, every vault fact asked about outside the vault, and every note asked about outside its location.

## What each world holds

Three environments, per [[Label Rule Table]]:
- **campus:** open. Locations lab, cafe, and the high-assurance vault.
- **studio:** carries out opinions and skills only. Location gallery.
- **severed floor:** carries out nothing. Location macrodata.

Each world runs two rounds:
- **S4:** a pair talks in the lab, the gallery and macrodata. Each conversation holds one fact and one opinion. Afterwards one of the pair tries to carry both into personal memory.
- **S5:** a pair talks in the vault. One tries to carry the opinion out. The other keeps a personal note there.

## Results

| Probe kind | Expected | No filter | Per-agent stores | memgate |
| --- | --- | --- | --- | --- |
| Witness, here | recall | 72/72 | 72/72 | **72/72** |
| Carried out, fact (lab) | recall | 24/24 | 24/24 | **24/24** |
| Carried out, opinion (lab, gallery) | recall | 48/48 | 48/48 | **48/48** |
| High-assurance witness, inside the vault | recall | 24/24 | 24/24 | **24/24** |
| Note, in its own location | recall | 6/6 | 6/6 | **6/6** |
| Carry-out refused, fact (gallery, macrodata) | no recall | 48/48 leaked | 48/48 leaked | **0/48** |
| Carry-out refused, opinion (macrodata) | no recall | 24/24 leaked | 24/24 leaked | **0/24** |
| Carry-out refused, high assurance (vault) | no recall | 24/24 leaked | 24/24 leaked | **0/24** |
| High-assurance witness, outside the vault | no recall | 72/72 leaked | 72/72 leaked | **0/72** |
| Witness, elsewhere | no recall | 144/144 leaked | 144/144 leaked | **0/144** |
| Note, elsewhere | no recall | 24/24 leaked | 24/24 leaked | **0/24** |
| Note, another agent's | no recall | 150/150 leaked | 0/150 | **0/150** |
| Non-witness | no recall | 960/960 leaked | 0/960 | **0/960** |
| **Leak rate** | | 100% | 23.2% | **0.0%** |
| **Recall at 20 / at 5** | | 100% / 100% | 100% / 100% | **100% / 100%** |

By scenario, memgate leaked 0/936 (S4) and 0/510 (S5).

## Audits

- **Carry-out.** In each world the answer key allows 6 of the 14 carry-out attempts:
  - allowed: the fact and the opinion from the lab, and the opinion from the gallery;
  - refused: the fact from the gallery, both items from macrodata, and the opinion from the vault.

  memgate refused the other 8 in each world, 24 in all. Each memgate bank held **16 documents, exactly as expected**: 8 conversations, 6 carry-outs and 2 notes. So refused carry-outs stored nothing, not even a stub.
- **Side effects.** The 108 recalls made inside the vault run first in each world, with a snapshot of each bank taken before and after. The snapshot counts nodes, links, documents, observations, the last write and operations. **Nothing changed for any system.** Hindsight recall is read-only at the bank level, so this confirms the baseline rather than separating the systems. It would catch a recall that set off consolidation, a reflect, or a write. memgate's own provenance record of those recalls goes to the vault's separate partition by design ([[memgate Core]]).

## Re-run with writes in Cedar (2026-09-30)

memgate only (the baselines are unaffected), after the high-assurance write seal and the carry-out location check moved into Cedar ([[memgate Proofs]] W1–W6, C4). Results were identical:
- 0 of 1,446 must-not probes leaked;
- recall 174/174 at 20 and at 5;
- 24 carry-outs refused (8 per world);
- 16 documents per bank;
- no side effects from the 108 recalls per world inside the vault.

Report: benchmark/reports/selective-env-2026-09-30.json.

**Again with high-assurance partitions (2026-09-30, run sel-env-2026-09-30b).** Each vault now has its own bank. Results were identical once more:
- 0 of 1,446 leaked;
- recall 174/174;
- 8 carry-outs refused per world;
- no side effects in either bank.

In each world the vault's bank holds exactly its 4 memories (2 conversations, 2 notes), and the shared bank holds none of them. Report: benchmark/reports/selective-env-2026-09-30b.json.

## Reading it

- **The permission rules hold end to end:**
  - the environment decides what may leave (S4);
  - the vault lets nothing out, whoever asks and from wherever (S5);
  - a note is readable only by its author, and only where it was written.
- **Per-agent stores fail exactly where context matters.** They keep other agents out, so non-witness and other-agent notes show 0 leaks. But an agent recalls everything it ever saw, wherever it is: vault secrets in the cafe, macrodata work at home. That is the 23.2%, and it is the case memgate exists for.
- **Refusal happens at write time, which matters.** memgate turns a forbidden carry-out away before it reaches the store, so nothing is left to filter later. The baselines store the carry-out, and from then on it is ordinary personal memory.
- **Recall is at ceiling, as in S1–S3.** Probes name the topic, and these worlds are small (8 conversations). This suite tests the rules, not retrieval difficulty.

## Limits

- **Retrieval-level leak check only** (exact code), as before.
- **Small worlds.** 3 × 540 probes. Environments with more locations, and more rounds, would test the per-location cache harder.
- **The runner prints the refusal count only after probing.** A run with `--skip-ingest` has no count, so here it was taken from the answer key and the bank document counts.

## Next

- Harder probes (indirect, paraphrased, multi-fact) and an answer-level leak check. These are the open items from every suite so far.
- S6 (hierarchy) and S7 (scale).
