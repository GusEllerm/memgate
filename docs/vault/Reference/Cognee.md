---
type: reference
status: active
authority: reference
summary: "Cognee (v1.6.1 @ eb90d03, Apache-2.0): knowledge graph + vector memory with dataset-level ACLs and a separate database per dataset; search runs once per readable dataset. Safe but coarse. Per-item labels break on name-keyed entities and union-merged tags, and search writes history and telemetry."
created: 2026-09-25
updated: 2026-09-25
tags: [memgate, reference, survey, cognee, knowledge-graph]
---

# Cognee

*Surveyed 2026-09-25 from [topoteretes/cognee](https://github.com/topoteretes/cognee) commit eb90d037 (v1.6.1), the [dataset permissions docs](https://docs.cognee.ai/core-concepts/multi-user-mode/permissions-system/datasets) and the [memify docs](https://docs.cognee.ai/core-concepts/main-operations/memify). Facts are as of that date. Listed in [[Architecture Survey]] and [[Memory System Landscape]].*

**Verdict so far.** It has the most real access control of any popular store, but only per dataset.
- **Dataset per label set:** workable and safe. Every readable dataset is searched separately, with its own LLM completion, and combining the results is left to us. It's coarse: thousands of label sets per agent would be slow, and entities are duplicated per dataset, which cuts links between locations.
- **Per-item labels in one dataset don't work.** Entities are keyed by name alone and tags are union-merged, so a shared "Project X" entity collects every location's tags. That is the same problem as [[Zep and Graphiti]].
- **Search writes history and telemetry,** which breaks side-effect-free recall unless patched.

## What it is

- **Version:** v1.6.1 (2026-09-24), Apache-2.0, still labelled "Beta". About 31k stars, fast-moving.
- **Stack:**
  - Python, SQLAlchemy, LiteLLM, FastAPI.
  - Graph: an embedded Kuzu fork (default), Neo4j, Neptune, Turso.
  - Vector: LanceDB (default), pgvector, Turso, Neptune Analytics.
  - Relational: SQLite or Postgres. It holds users, ACLs and search history, and is always shared.
- **Self-hosting:** fully, embedded by default. Docker and MCP are also available.

## Pipeline

- **add:** ingests data, with optional node-set tags.
- **cognify:**
  - Classifies and chunks documents (no LLM).
  - One LLM call extracts entities, relations and a summary per chunk.
  - Writes nodes, edges and embeddings.
  - Optional: provenance recording, contradiction detection (LLM) and temporal supersession.
- **memify:** the default embeds triplets, with no LLM. Optional LLM pipelines:
  - rewrite entity descriptions in place;
  - add inferred edges;
  - build hierarchical summaries;
  - fold feedback weights and session answers back into the graph.
- **Search:** 20 types. Chunk, summary, lexical and Cypher search only retrieve; the completion types call an LLM.

## Access control

- **Principals:** users, tenants and roles. ACL rows are (principal, permission, dataset), with read, write, delete and share. The docs say permissions are "defined at the dataset level, never for individual documents."
- **Backend isolation:** on by default. Each dataset gets its own graph and vector database, or its own schema on shared Postgres.
- **Enforcement:** picks the database, never filters within one. A search first resolves the readable datasets, raising an error if any requested dataset is forbidden, then searches each in isolation.
- **Results:** one per dataset, not merged.
- **With isolation off,** dataset parameters are ignored and search spans all data.

## Lineage

- **Links:** chunk → document ("is part of") and summary → chunk ("made from"). Ownership is reference-counted, so shared output is deleted only with its last owner.
- **Source fields:** every data point records its source user, node set, pipeline and task.
- **Entities are keyed by name alone,** so "Project X" is one node across a dataset's documents, and tags union on upsert.
- **Mixing:** consolidated descriptions and global summaries mix sources through the LLM, with no label propagation.

## Fit with our model

| Requirement | Fit | Why |
| --- | --- | --- |
| Dataset per label set | Safe but coarse | Cedar's allowed label-set IDs become the dataset list. Costs: N searches and N completions per query, an engine cache of 6 by default, duplicated entities (breaks cross-location provenance). Hundreds of datasets plausible on Postgres schemas; thousands slow (estimate, not measured) |
| Per-item labels | Breaks | Node-set filters are pushed into LanceDB with one all-of or any-of operator per call, can't express our rule, and are caller-chosen, not an ACL. Name-keyed entities with union-merged tags make shared entities readable by anyone holding any one tag |
| Union inheritance | Needs a fork | Stop merging across label sets, e.g. by putting the label-set ID into entity IDs |
| Recall side effects | Breaks | Each search writes a history row to the shared database, sends telemetry, may update last-accessed, and memify can later write session answers into any writable dataset |
| Export | Good | Per dataset, as re-importable cogx, JSON, GraphML or Cypher, optionally with permissions; tags and source fields travel as properties |

## For benchmarking later

- **Self-reported:** BEAM LLM-judge 0.79 at 100K (20 questions, one conversation) and 0.67 at 10M (exploratory) ([report](https://github.com/topoteretes/cognee/blob/main/cognee/eval_framework/beam/REPORT.md)).
- **Fairness:** a dataset-per-label-set setup needs the fan-out cost measured.
