---
type: reference
status: active
authority: reference
summary: "Honcho (v3.2.1 @ c8e97bc, AGPL server): peer-centred memory where conclusions live in (observer, observed) collections copied at write time. Strong derived-from lineage and read-only recall, but no user labels, views are copies rather than read-time checks, and there's no export. Fork effort moderate to high."
created: 2026-09-25
updated: 2026-09-25
tags: [memgate, reference, survey, honcho]
---

# Honcho

*Surveyed 2026-09-25 from [plastic-labs/honcho](https://github.com/plastic-labs/honcho) commit c8e97bc5 (v3.2.1), the [scopes docs](https://honcho.dev/docs/v3/documentation/features/advanced/scopes) and the [benchmark post](https://plasticlabs.ai/blog/research/Benchmarking-Honcho). Facts are as of that date. Listed in [[Architecture Survey]] and [[Memory System Landscape]].*

**Verdict so far.** Its peer model looks like our participant labels, but it works differently.
- **How it works:** each observer's view is a copy made at write time, not a label checked at read time. The copies sit in collections keyed by (observer, observed).
- **What's missing:** conclusions carry no user labels, derived conclusions get a wrong session stamp, and there is no export.
- **What's reusable:**
  - the derived-from lineage table;
  - transitive retraction when evidence is removed;
  - read-only recall;
  - per-pair views, as a baseline for diversity of opinion.
- **Effort:** a fork is moderate to high work, because the collection key runs through everything.

## What it is

- **Version and licence:** v3.2.1 (2026-09-24). The server is AGPL-3.0; the SDKs are Apache-2.0.
- **AGPL for us:** running a modified copy for internal research creates no obligation. Source must be offered only if outside users reach it over a network.
- **Stack:**
  - Python 3.13, FastAPI.
  - Postgres with pgvector (HNSW) plus Redis. Qdrant, turbopuffer or LanceDB can replace pgvector.
  - Anthropic, OpenAI and Gemini backends.
- **Scale:** about 52k lines, weekly releases.
- **Self-hosting:** Docker, including a mock LLM for runs without API keys.

## Data model and derivation

- **Hierarchy:** workspace → peer → session → message.
- **Conclusions** are documents in a collection keyed by (observer, observed). A peer's view of itself is where observer equals observed.
- **Deriver:** each new message queues work for the sender (if it observes itself) and for every co-member that observes others. One LLM call per batch writes conclusions, then **copies them into every observer's collection**. So different observers get copies of the same reading, not separate readings.
- **Other LLM jobs:**
  - A dreamer runs deduction and induction per (observer, observed) pair and refreshes the peer card.
  - A summariser runs every 20 and every 60 messages.
  - The dialectic chat endpoint is an agent loop at query time.

## Scoping

- **Queries** are fixed to one (workspace, observer, observed) collection, with filters inside the pgvector SQL. No HNSW iterative scan is set, so selective filters can return fewer results.
- **External stores** get a namespace per pair, then SQL re-filters the IDs returned.
- **Scopes** are named session sets. Each has a hidden peer that builds its own view. The docs say: "Scopes are a recall boundary, not an authorization boundary."
- **Auth:** JWT claims for workspace, peer and session. Off by default.

## Lineage

- **Explicit conclusions** store their message IDs and session, and never deduplicate across sessions.
- **Derived conclusions** link to their parent conclusions through a sources table. Invented source IDs are removed before saving (since v3.2.0).
- **Sessions mix.** Derived conclusions can mix sessions and are deduplicated across them. The dreamer stamps them with the collection's newest session, so the session field is not a real label.
- **Transitive retraction:** removing a scope soft-deletes everything derived from its evidence.

## Fit with our model

| Requirement | Fit | Why |
| --- | --- | --- |
| Participants | Partial | Observers present get copies at write time; there's no read-time "reader is a participant" check |
| Location | Poor | A scope's view belongs to the scope's peer, so "agent A while in location L" can't be expressed |
| Personal memory | Good | The (A, A) collection; writes are gated by the "observe me" setting and a workspace key |
| Custom labels | Missing | Conclusions accept only content, observer, observed and session |
| Union inheritance | Needs a fork | A label-set column, a union computed from sources, and a dreamer and dedup that respect label sets. The per-observer copying would be replaced by one copy plus a pre-filter |
| Recall side effects | Good in the database | Read-only sessions. But it calls the LLM and embedding providers and sends telemetry (CloudEvents, Langfuse, Sentry), which must be off or local in high-assurance partitions |
| Export | Missing | Paged list endpoints (with source IDs) or a database dump only |

## For benchmarking later

- **Self-reported (2025-12-19):** LongMemEval-S 90.4% (92.6% with Gemini 3 Pro), LongMemEval-M 88.8%, LoCoMo 89.9%, BEAM 0.406–0.649.
- **Models:** ingestion used gemini-2.5-flash-lite and chat used claude-haiku-4-5.
- **Eval code:** in plastic-labs/honcho-benchmarks.
- **The authors' own caveat:** short-context scores are no longer meaningful.
