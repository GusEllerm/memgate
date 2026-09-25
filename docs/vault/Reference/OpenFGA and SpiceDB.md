---
type: reference
status: active
authority: reference
summary: "Zanzibar-style engines (OpenFGA v1.21.0, SpiceDB v1.56.2): our rule fits but needs a workaround for 'all labels' and per-turn context; listing tops out around 1000 results; 10–95 ms per query at only 10–20k label sets; OpenFGA's in-memory store couldn't load 100k label sets in 20 minutes. No formal verification. They fight our flat attribute model."
created: 2026-09-25
updated: 2026-09-25
tags: [agentic-memory, reference, survey, policy-engine, rebac]
---

# OpenFGA and SpiceDB

*Surveyed 2026-09-25. The agent pinned OpenFGA v1.21.0 (ab557c55), SpiceDB v1.56.2 (be3e1ef6), fga CLI v0.8.1 and zed v1.2.1, and benchmarked both engines in Docker on in-memory stores, checking results against brute force. Sources: releases for [OpenFGA](https://github.com/openfga/openfga/releases) and [SpiceDB](https://github.com/authzed/spicedb/releases), the [CNCF incubation post](https://www.cncf.io/blog/2025/11/11/openfga-becomes-a-cncf-incubating-project/), OpenFGA docs on [contextual tuples](https://openfga.dev/docs/interacting/contextual-tuples), [ListObjects](https://openfga.dev/docs/getting-started/perform-list-objects), [relationship queries](https://openfga.dev/docs/interacting/relationship-queries), [consistency](https://openfga.dev/docs/interacting/consistency) and [testing](https://openfga.dev/docs/modeling/testing), the [ListObjects algorithm post](https://auth0.com/blog/openfga-improved-listobjects-algorithm/), and SpiceDB docs on [schema](https://authzed.com/docs/spicedb/concepts/schema), [caveats](https://authzed.com/docs/spicedb/concepts/caveats), [querying](https://authzed.com/docs/spicedb/concepts/querying-data), [performance](https://authzed.com/docs/spicedb/ops/performance), [consistency](https://authzed.com/docs/spicedb/concepts/consistency), [best practices](https://authzed.com/docs/best-practices), [validation](https://authzed.com/docs/spicedb/modeling/validation-testing-debugging) and the [scale benchmark](https://authzed.com/blog/google-scale-authorization). Facts are as of that date. Listed in [[Architecture Survey]].*

**Verdict so far.** They work, but they fight our model.
- **Model mismatch:** our read rule is a flat condition over attributes. These engines are built for walking relationship graphs (hierarchies, groups, delegation).
- **Awkward to express:** "all identity and location labels granted" needs a double-negation workaround. Per-turn context needs special handling.
- **Listing is capped** at around 1,000 results per call. Queries took 10–95 ms at just 10–20k label sets.
- **Loading is slow:** OpenFGA's in-memory store couldn't load 100k label sets in over 20 minutes.
- **No formal verification.**
- **When they would win:** only if grants become genuinely relational.

## What they are

| | OpenFGA | SpiceDB |
| --- | --- | --- |
| Version, licence | v1.21.0 (2026-09-20), Apache-2.0, CNCF Incubating, 37 adopters | v1.56.2 (2026-09-11), Apache-2.0 |
| Datastores | Memory, Postgres, MySQL, SQLite | Spanner, CockroachDB, Postgres, MySQL, memory |
| In-process | Go library | Embedded mode (v1.56), Check only: no listing |
| Per-turn context | Contextual tuples (up to 100 per request), CEL conditions | Caveats (CEL) or written relationships; no contextual tuples |
| Listing | ListObjects: 1,000-result cap, 3 s deadline, no pagination | LookupResources: streams with a cursor, 1,000 per call; docs say it gets heavy above about 10k results |

Also noted: Permify is AGPL-3.0. Ory Keto documents no listing API and no intersection or exclusion operators.

## Modelling our rule

"All identity and location labels granted" uses De Morgan's law: allowed = not (any label not granted). OpenFGA's traversal operator means "any", not "all". SpiceDB has an "all" form, but it wasn't tested on empty sets. This OpenFGA model passes its tests, including listing:

```
type ctx
type agent
  relations
    define actor: [ctx]
    define present: [ctx]
    define not_actor: [ctx:*] but not actor
type location
  relations
    define here: [ctx]
    define not_here: [ctx:*] but not here
type label_set
  relations
    define ident: [agent]
    define loc: [location]
    define participant: [agent]
    define no_participant: [ctx:*]
    define with_ok: present from participant or no_participant
    define violation: not_actor from ident or not_here from loc
    define readable: with_ok but not violation
```

- **Stored records:** the label-set links, plus a wildcard record per agent and location. **Gotcha:** without that wildcard record, the exclusion silently grants access. A test caught this.
- **Per request:** 2 plus the number of participants in contextual tuples.
- **Reserved words:** with and self can't be relation names.
- **SpiceDB:** the equivalent schema passes its validator (18 assertions).

## Benchmark (M-series laptop, in-memory stores, 30 queries, 5 participants per turn, no mismatches against brute force)

| Label sets / agents / locations | OpenFGA, contextual tuples (p50) | SpiceDB, caveats | SpiceDB, written context (write + list) |
| --- | --- | --- | --- |
| 10k / 200 / 100 (44 results) | 9.6 ms | 28.6 ms | 1.8 ms + 22.6 ms |
| 10k / 50 / 10 (248 results) | 10.9 ms | 95.5 ms | 1.7 ms + 75.0 ms |
| 20k / 200 / 100 (88 results) | 19.2 ms | 95.3 ms | not run |

- **Scaling:** latency grows roughly linearly with the number of label sets.
- **Loading:** OpenFGA's in-memory writes slowed badly. 76k records took 35 s. The 100k set (about 380k records) was still loading after 20 minutes and was killed. Retest on Postgres.
- **Staleness:** SpiceDB's fastest consistency mode returned stale, incomplete results right after a bulk write. They were correct after its 5 s window, or with an "at least as fresh" token.

## Fit

- **Per-turn context:**
  - OpenFGA's contextual tuples need no writes per turn, so they fit best.
  - SpiceDB's written context costs 2 plus the number of participants in writes and deletes per agent per turn, and needs a consistency token on every read.
  - SpiceDB caveats need no writes, but were slowest.
- **Environment write rules** (dropping labels, personal-memory writes, *Severance*) sit outside both engines. At most they could be extra checks.
- **Beyond 100k label sets,** an in-process bitmap index would likely be orders of magnitude faster.

## Verification

- **Tooling:** OpenFGA model tests cover checks, listing and user listing with context. SpiceDB's validator covers assertions, including caveated results, and the expected access paths over fixture data.
- **High-assurance property:** neither offers formal or exhaustive verification. It would rest on correct labelling at write time plus a separate test harness.

## For benchmarking later

- **Published numbers:** SpiceDB's "1M QPS, 5.76 ms p95" covers single checks only, not listing, and its cache hit rate rose to about 96% under load. OpenFGA's caches are off by default, and listing is only partly cached.
- **Consistency:** SpiceDB handles the "new enemy" problem with tokens. OpenFGA offers only a higher-consistency mode.
- **Next runs:** Postgres backends, 100k+ label sets, many concurrent contexts, and deep relationship chains.
