# Integrating memgate

For the agent or developer wiring memgate into a host application (for example Knowledge Ranch). Read it end to end before changing the host. The `integrate-memgate` skill in this repo's plugin walks the same steps.

## What memgate does

memgate decides which memories an agent may recall, store and carry out, from the **context** it is in:

- **who** is acting;
- **where** it is (a location, in an environment);
- **who else is present**.

It sits in front of a memory system (today [Hindsight](https://github.com/vectorize-io/hindsight) 0.10.1). Every memory carries a label set formed from the context it was stored in, and every recall is filtered to the label sets that context may read.

The rules, all enforced:

| Rule | Meaning |
| --- | --- |
| Witnesses, in place | A conversation is recalled only by someone who was present, and only in the location where it happened. |
| Personal memory | Readable by its owner everywhere, by no one else. |
| Carry-out | Content becomes personal memory only if every environment it came from lets that memory type out, and only where the source is readable. |
| High assurance | Nothing formed in a high-assurance location is ever recalled outside it; nothing is carried out of it; anything written inside it stays inside. Each high-assurance location is stored in its own partition. |
| Fail closed | Unknown agents and locations are refused everything; errors refuse rather than allow. |

The Cedar policies are proved with Cedar's symbolic compiler, and each rule holds for every possible request. They are tested on random worlds and live, and benchmarked: 0 leaks in about 11,000 locked probes, and no measurable recall cost on LoCoMo.

## The contract: what memgate trusts, and what the host must do

memgate trusts the **Context** it is given. It cannot know where an agent really is or who is really present; only the host can. Everything below is the host's job. If any item is skipped, memgate's guarantees do not hold.

1. **The host builds every Context from verified facts.** An agent never supplies its own agent id, location or participants. If agents run as separate processes, the host must verify the caller's identity (per-agent credentials) and take location and participants from its own simulation state. A common design is a short-lived context token signed by the host and bound to the agent's credential, reissued whenever the agent moves.
2. **Agents never reach memgate or the memory store directly.** memgate runs inside a host-controlled service. The shared secret (`MEMGATE_SECRET`) and the memory store's port (loopback by default) are out of agents' reach. An agent that can read the secret can impersonate anyone.
3. **The world file mirrors the host's world.** Every agent, location and environment the host uses must be listed before it is used. Unlisted ones are refused. Regenerate the file when the world changes. Write it to a temporary name and rename it, so memgate never reads a half-written file. memgate picks up changes within a second, with no restart. A world that lists no locations or agents yet is valid (0.8.2): a fresh deployment's `memgate serve` starts on it and reports healthy, every memory call is refused until the world lists the agent and the location, and the server and client pick up the populated world when the host rewrites the file, with no restart.
4. **The host clears or seals an agent's working context when it leaves a location,** above all a high-assurance one. memgate filters what an agent can *recall*. What is already in its prompt or scratchpad goes with it unless the host drops it.
5. **The host scopes tools by the same labels.** Files, databases, messages, code execution and web access are all ways to move information that memgate never sees. Give storage the location's labels. Turn off outbound tools inside high-assurance locations.
6. **Logs, traces and transcripts are labelled data.** Store them per high-assurance partition, as memgate does for its own provenance.
7. **Memory type at carry-out** (fact, opinion, skill, episode) is the agent's own classification. memgate trusts it and records it in the audit log. Selective environments (for example "opinions only") are only as strong as that classification.

## Mapping the host's world

A world file is JSON. Check it with `memgate check-world world.json`.

```json
{
  "environments": [
    {"id": "campus"},
    {"id": "studio", "carry_out": ["opinion", "skill"]},
    {"id": "severed-floor", "carry_out": []},
    {"id": "chatham", "carry_out": ["fact", "opinion", "skill"], "min_class": "unattributed"}
  ],
  "locations": [
    {"id": "lab", "environment": "campus"},
    {"id": "vault", "environment": "campus", "high_assurance": true},
    {"id": "gallery", "environment": "studio"}
  ],
  "agents": ["ada", "bo", "cy"]
}
```

| Concept | Meaning | Host decision |
| --- | --- | --- |
| Environment | A set of locations sharing one carry-out rule | Which memory types may leave: `carry_out` lists them. Omitted means all four; `[]` means nothing leaves, and (0.7.0) what already left its locations is withheld everywhere but there until the list opens again (the source seal). Optionally `min_class` (0.5.0): carry-outs from its locations must name at least that class (see "Classes of personal memory") |
| Location | Where conversations happen; every memory formed there is bound to it | Which locations exist, and which are high assurance |
| High assurance | Outbound only: nothing leaves, anything inside stays inside; personal memory may still be recalled there | Which locations need it (secrets, sensitive work) |
| Agent | An identity with its own personal memory | Every agent id the host will ever pass |
| Participants | Who is present in a conversation (the Context) | Taken from the simulation at the time of each call |

Ids are free strings, except that `--ha--` is reserved.

## Install and run

```sh
# the server side: memgate with the Hindsight version its validator is tested against (its own environment)
pip install "memgate[hindsight] @ git+https://github.com/GusEllerm/memgate@v0.8.2#subdirectory=memgate"
# the host side: the client only (cedarpy is its one dependency); add [async] for AsyncHindsightMemory (httpx)
pip install "memgate[async] @ git+https://github.com/GusEllerm/memgate@v0.8.2#subdirectory=memgate"

export MEMGATE_WORLD=/srv/host/world.json
export MEMGATE_REGISTRY=/srv/host/memgate/registry.sqlite     # label-set registry, shared by both sides: a SQLite path, or postgresql://... (0.6.0)
export MEMGATE_SECRET=$(memgate secret)                        # store it where only the host can read it
export MEMGATE_LLM_BASE_URL=https://your-llm/v1 MEMGATE_LLM_MODEL=your-model MEMGATE_LLM_API_KEY=...

export MEMGATE_DB=pg0://memgate                                # or postgresql://... (needs vector and pg_trgm)
memgate serve --socket /srv/host/memgate-run/memgate.sock      # recommended: a Unix socket in a private (0700) dir
# or: memgate serve --port 8889                                # a loopback port
```

- **`memgate serve`** starts Hindsight with memgate's validator: the second lock, inside the store. It refuses a non-loopback bind unless you pass `--allow-remote`. It turns off Hindsight's LLM traces, which would hold memory content outside the partitions.
- **Prefer a Unix socket** (`memgate serve --socket <dir>/memgate.sock`; clients use the address `unix:<dir>/memgate.sock`). The client sends the shared secret with every request, so it must know it is talking to memgate's server. Over a port, any local process that binds it first, or after the server stops, would receive the secret. Over a socket, the client checks before every request that the socket's directory is private (0700) and owned by the same user, so only that user's processes could have created it. `serve` creates the directory private, and refuses one that isn't. Socket paths are limited to about 100 bytes. Run the host and the server as the same user; in Docker, share the socket's directory as a volume between the two containers instead of using a network. Requests never go through an HTTP proxy, whichever transport you use.
- **Always start Hindsight through `memgate serve`, never `hindsight-api` directly.** Hindsight applies the first `.env` it finds walking up from its working directory, over its environment. A stray or planted `.env` could drop the validator, change the database or turn traces on. `memgate serve` starts Hindsight in a private directory (`--workdir`; by default `.memgate-serve` beside the registry, mode 0700) holding an empty `.env`, and refuses to start if that file isn't empty. It also fingerprints every setting it forces, and the validator refuses to load (so Hindsight won't start) if any was changed. In a container, give that directory a volume or let `serve` create it, and don't add a `.env` to it.
- **Hindsight's log holds no memory text.** Hindsight 0.10.1 logs the start of every recall query at INFO (conversation text, and from inside a high-assurance location its sealed text). `memgate serve` sets Hindsight's log level to WARNING (fingerprinted like its other settings, so a `.env` cannot raise it), and the validator redacts recall queries from whatever Hindsight logs at any level, including a failed recall's ERROR line. `--hindsight-log-level info` (or `MEMGATE_HINDSIGHT_LOG_LEVEL`) turns the operational log back on for debugging; serve then warns that the log is labelled data, since memory text other than queries may appear in it.
- **Consolidation timing:** Hindsight derives observations from stored facts in a background consolidation it schedules right after each write. Facts are recallable at once; observations follow within seconds (0.4.4 and later; before 0.4.4 the validator refused that schedule request and Hindsight's reconcile sweep ran consolidation up to five minutes later, logging "Failed to submit consolidation task ... admin only" each time). Consolidation stays within one label set.
- **Readiness:** don't detect startup from the server's log (at the default warning level uvicorn prints no "running on" line). Probe `GET /health` over the socket or port until it answers 200, or retry the client's `create_bank()` until it stops raising; the first request after start can take a while because the embedder loads.
- **The LLM** is used by Hindsight to extract and consolidate memories (any OpenAI-compatible endpoint). **Embeddings** are local (BAAI/bge-small-en-v1.5 by default).
- **A torch-free server (0.6.0, completed in 0.8.1):** torch is only there for Hindsight's local embedder and cross-encoder reranker, and it is most of the server's resident memory. Three embedders: `--embeddings-provider local` (sentence-transformers, torch; the default), `onnx` (onnxruntime, no torch; `--embedder` then names a Hugging Face repo with an `onnx/model.onnx` export, the default bge-small has one) and, since 0.8.1, `openai` (a hosted OpenAI-compatible endpoint, no model in the process: `--embeddings-base-url` e.g. `https://openrouter.ai/api/v1`, `--embeddings-model`, the key from `MEMGATE_EMBEDDINGS_API_KEY` else `MEMGATE_LLM_API_KEY`, optionally `--embeddings-dimensions`; all forced and fingerprinted, so a `.env` cannot redirect them; every memory text and every recall query is sent to that endpoint, where the local and onnx embedders keep queries on the host). Three rerankers: `--reranker local` (a cross-encoder, torch), `flashrank` (a small ONNX cross-encoder: on the benchmark within two points of the local one) and `rrf` (no reranking: halves recall on indirect questions). Install `memgate[hindsight]` for the local models or `memgate[hindsight-slim]` (Hindsight's torch-free package with its onnx extra, plus flashrank) for `onnx`/`openai` with `flashrank`/`rrf`; `memgate serve` checks at start that the chosen providers' packages are importable and names the extra to install if not. It prints one JSON line (`event: serve`) with the live embedder, model, base URL, dimensions and reranker, so the host's logs show which is in use. Changing the embedder changes the vector size: Hindsight refuses to start on a database whose units were embedded at another size while rows exist (its error names the fix: delete the memory units, or go back to a model of that size), and alters the column when the tables are empty; so switch embedders on a fresh database, or accept re-ingesting everything. Resident memory per configuration is in the changelog (0.8.1).
- **Version handshake (0.6.0):** the client sends its release with every request. The server refuses a client newer than itself (upgrade the server first) and, with `memgate serve --min-client-version X.Y.Z`, any client older than that or sending no version (a stale worker). `HindsightMemory(..., check_version=True)` makes one gated request per server at construction, so a mismatched worker fails at boot with `VersionMismatch` rather than on its first write. The handshake protects from 0.6.0 onward: a 0.5.x server does not read the header, and a 0.5.x client sends none (it is refused only when the server sets a minimum).
- **Logging (0.6.0):** memgate logs one JSON line per write, recall, refusal and forget, with ids, counts, label-set ids and reasons, never memory or query text. The server writes them to stdout itself (independent of Hindsight's log level); the client logs to the Python logger `memgate`, which the host enables like any other library logger.
- **The host process and the server must see the same three settings:** `MEMGATE_WORLD`, `MEMGATE_REGISTRY` and `MEMGATE_SECRET`.
- **The database:** `pg0://name` is an embedded Postgres. For your own server, use a `postgresql://` URL in `MEMGATE_DB`, not the `--db` flag, so the password stays out of the process list. Put the password in the user part (`postgresql://user:password@host/db`): memgate and Hindsight both mask it in their output. `memgate serve` refuses a password in the query (`?password=`), because Hindsight 0.10.1 logs the query in clear. Give memgate its own database role, with access to its database only, so the server can't reach the host's other data. The database needs the `vector` (pgvector) and `pg_trgm` extensions; pre-create them if Hindsight's role may not.
- **World changes:** both sides re-read the world file when it changes, checked at most every `MEMGATE_WORLD_CHECK_S` seconds (default 1; `memgate serve --world-check-interval`). In the host, call `gate.refresh(force=True)` right after writing the file. A memory call to something created within that interval may be refused by the server; retry once.
- **The registry** is a SQLite file (WAL) or, since 0.6.0, a PostgreSQL database (`MEMGATE_REGISTRY=postgresql://user:password@host/db`, with `memgate[postgres]` installed on both sides; tables go in a `memgate` schema, so it can share Hindsight's database). Any number of host processes may write it (for example several web workers), and the server only reads it. SQLite works across processes and containers on one host; never put it on NFS or EFS, or on a macOS Docker Desktop bind mount shared with a host process. Use PostgreSQL when API workers run on more than one host; `PostgresRegistry.copy_from(Registry(path))` migrates a SQLite registry (ids are content-addressed, so it is a re-registration).
- **A separate server for high-assurance partitions** (optional, for isolation): run a second `memgate serve --scope partitions` with its own port and database, and the first with `--scope shared`. Both use the same world, registry and secret. Pass `partition_url=` to the client. Each server refuses the other's banks. Both can use the same LLM (Hindsight 0.10.1 cannot give one bank its own LLM, so a different LLM for high assurance needs this split anyway).

## The API

```python
from memgate import Context, Gate
from memgate.adapters.hindsight import HindsightMemory

gate = Gate.from_env()                                     # world (followed for changes), registry, secret
mem = HindsightMemory(gate, bank="ranch", base_url="unix:/srv/host/memgate-run/memgate.sock")   # or http://127.0.0.1:8889
mem.create_bank()

ctx = Context(agent="ada", location="lab", participants=("ada", "bo"))    # built by the host, from verified facts
```

| Call | Use it when | Notes |
| --- | --- | --- |
| `mem.recall(ctx, query, k=20)` | The agent needs to remember something | Returns a `RecallBatch` of `Recalled` (text, label set, date, write id), best first, only what `ctx` may read. `.recall_id` is set when provenance is on |
| `mem.remember(ctx, text, when=None, about=None, turns=(), key=None)` | Something was said or seen in a conversation | Stored under `ctx`'s location and participants. `turns` links it to what was said (provenance). Returns the write id |
| `mem.keep_note(ctx, text, key=None)` | An agent's private note that should stay where it was written | Readable only by its author, only in that location |
| `mem.carry_out(ctx, text, memory_type, source=None, source_writes=(), key=None, cls=None)` | An agent takes something with it into personal memory | `source` is what the content was formed under. Pass the `Recalled` item itself to carry out something recalled (its label set, and its write for provenance), or a label set or its ID. It defaults to `ctx`'s conversation. It must be readable in `ctx`. Raises `PermissionError` if the environment forbids it |
| `mem.say(ctx, text, recalls=[recall_id, ...])` | An agent speaks | Records which recalls it drew on, so later memories trace back (needs a `ProvenanceLog`) |
| `mem.personal(agent)` | The owner wants to see what the agent kept | Every item in the agent's personal sets (plain, by class, by source), text as kept, month, kind; since 0.7.0 also `source` (the location it was carried out of, `None` for items kept before 0.7.0) and `withheld` (its source currently lets nothing out, so it is recalled only there). Admin, host-trusted: the host verifies the owner (0.6.0) |
| `mem.forget(agent, write_id)` | The owner wants one kept item gone | A hard delete of that item and what the store derived from it; refused unless the write id is in that agent's personal memory. The host must also stop re-sending it (0.6.0) |
| `mem.stats(agent=None, location=None)` | An operator or owner wants counts | Per partition: pending work, last consolidation; per personal set of `agent` (0.6.0) or conversation set of `location` (0.8.0): memories, derived items, writes, last write |
| `mem.location(location)` | The tree's owner wants to see what the place remembers | Every item in the location's conversation sets ({loc:L, with:...}), derived ones included, each with `participants`, text as kept, month, kind. Agents' private notes bound to the place are not listed. Admin, host-trusted: the host decides who may see a place's memory (0.8.0) |
| `mem.forget_location(location)` | The tree's owner wants the place's memory gone | A hard delete of every write in those sets with what the store derived from them, and of the private notes bound to the place (purged, never listed); personal sets carried out of it are left alone (use `forget`). Idempotent; returns counts `{sets, writes, derived, notes}`. Host-trusted; memgate does not require the location to be held (0.8.0) |

- **Idempotent writes:** pass `key=` (any string the host chooses, e.g. its own segment id) to `remember`, `keep_note` or `carry_out`. The write id is derived from the key and the label set, so re-sending the same key under the same label set (same location, same participants; same author for a note) replaces the earlier write instead of storing it twice: Hindsight upserts by that id, and a byte-identical re-send extracts nothing new. A host that records at least once (an outbox drained after a crash) gets exactly-once storage this way. The id carries the label set, and the server refuses a write id minted under another label set, so a key can never reach another conversation's memory. An agent's personal memory (carry-outs) is one label set, so a carry-out key must be unique across everything that agent ever carries out, and a retry must re-send the same text under the same key (store the chosen items, then write them).
- **Classes of personal memory (0.5.0).** `carry_out(..., cls="unattributed")` files the item in the agent's class set, `personal_labels(agent, "unattributed")` = {self:A, class:unattributed}, instead of {self:A}. Use it for items that must never be consolidated with the agent's other personal memory, for example items kept without names from a place where no one may be named: the memory system's consolidation merges and resolves references within a label set, and would put a name back if both lived in one set.
  - **Reading** is exactly as for {self:A}: the owner recalls it everywhere, nobody else does. The policies never see the class, so nothing about who may read changes. `Recalled.label_set` tells the host which set an item came from (compare it with `personal_labels(agent, cls).id`, or read `gate.registry.get(id).classes`).
  - **The host chooses the class.** memgate never derives it. Two rules guard it, both in the client, since the server never sees a carry-out (only the personal write it produces): content whose source carries a class may not go to a less strict class (any source form: a `Recalled` item, a label set or its id), and an environment's `min_class` must be met. Neither can catch a host that declares a classless source for content that came from a class set.
  - **What keeps the sets apart** is the memory system's consolidation scope: Hindsight consolidates within one tag, and a class set is a different tag. That is outside the policies' proofs. `memgate conformance` checks it on the live deployment (`class-apart`).
  - **One class for now** (`labels.CLASSES`), on one ordered scale, so each agent has at most one set per class. A class is allowed only beside a self label (personal memory), never on conversations.
  - **Upgrading:** servers first, always (the version handshake refuses a client newer than its server): move every `memgate serve` to 0.5.0 before any client writes a class, then the clients, restarting every worker together. A 0.4.x server reads the whole registry on every write and fails every write, not only classed ones, once one class row exists; a 0.4.x client fails on any class set it looks up. Add `min_class` to the world file only once the server is on 0.5.0 (older `serve` and `check-world` reject unknown keys).
  - **Rolling back to 0.4.x** after a class row exists needs those rows removed from the registry, with every memgate process stopped: `DELETE FROM label WHERE label_set IN (SELECT label_set FROM label WHERE kind = 'class'); DELETE FROM label_sets WHERE labels LIKE '%"class:%';` (run the first statement first). The class sets' memories stay in the store, unreachable (failing closed, not leaking); upgrading again and writing to a class set re-registers it, and its memories come back, since ids are content-addressed. From 0.5.0 on, a label set with a kind or class the running version doesn't know is skipped (never readable or writable there) instead of failing every call.
- **Classes and consolidation (0.6.0):** the world file may set, per class, whether the store consolidates that class's sets: `"classes": [{"id": "unattributed", "consolidate": false}]`. With `false`, Hindsight builds no observations over those sets (set per partition, so the class's items are kept in a partition of their own by the store). The default is to consolidate, as before. Items carried into the class set before the flag was set (or by a 0.5.x client) stay in the shared partition; recall finds them there, and since 0.6.2 so do `personal` and `forget`, which look in every partition the set may live in. No migration is needed when the flag flips.
- **The source seal (0.7.0).** A carry-out records where it came from: `carry_out` files the item under {self:A, class?, src:L}, L being the Context's location, and the policies withhold it wherever L's environment currently lets nothing out (`carry_out: []`) except in L itself. So a host that closes a tree holds everything its agents carried out of it, including what the store derived from those items (derivation never crosses label sets), and releases it all by opening the list again; nothing is deleted or rewritten, and both locks enforce it (proved: [[memgate Proofs]] R8, R9, W7). An item carried out under one tree's rule and a tree closed later: withheld until it is opened, as Gus ruled; carry-outs remain final in every other way (a narrower list still lets the earlier item through). Nothing new leaves a held location either, as before. A location removed from the world file is not held: what was carried out of it stays readable, as any other carry-out.
  - **Items kept before 0.7.0** have no source and are never withheld. `memgate attach-sources <agent> <mapping.json> --bank <name>` (or `mem.attach_source(agent, write_id, location)`) gives them one from a host-supplied mapping `{write_id: location}`, such as CHORUS's lineage table: each item is re-written under its sourced set with its text as the store kept it (for Hindsight, its extracted units joined), its month and a provenance link to the old write, as a write made at that location, and the unsourced copy is forgotten; the new write id is `personal` reports afterwards. `--dry-run` counts without writing. The host must update its own record of the write id.
  - **Upgrading:** servers first, as always. A 0.6.x server does not know the `src` label kind, so it refuses writes to sourced sets (every carry-out from a 0.7.0 client) until it is on 0.7.0; a 0.6.x client sends no source, and its carry-outs keep working against a 0.7.0 server as unsourced items. Move every `memgate serve`, then the clients.
- **The location's view and purge (0.8.0):** `location(L)` and `forget_location(L)` are host-trusted like the owner's view: memgate checks only that L is a location in the world and touches only L's own sets. Who may see a place's memory, and who may empty it and when (CHORUS: anyone who can read the tree sees it; its owner purges it once the tree is held), is the host's decision. A purge does not stop the host's recorder: new conversations at L are stored again as fresh writes, and a host that re-sends keyed writes on retry must not replay the purged ones. `memgate inspect-location <loc> --bank <name>` and `memgate forget-location <loc> --bank <name> --yes` do the same from a terminal.
- **The owner's view and forget** are host-trusted operations: memgate checks that a write id belongs to the agent's personal memory (plain, any class, any source), nothing more; who may ask on that agent's behalf is the host's decision, like every Context. Forget is a hard delete (database backups keep the text until they age out). A host that re-sends keyed writes on retry must tombstone its own record of a forgotten item, or the next replay brings it back. `memgate inspect <agent> --bank <name>` and `memgate forget <agent> <write-id> --bank <name> --yes` do the same from a terminal, with the server's `MEMGATE_*` settings and `MEMGATE_URL`.
- **Async hosts:** `AsyncHindsightMemory` (same arguments, `await` every call; use `async with`, or call `aclose()`) has the same API and the same decisions. Otherwise wrap the sync client in `asyncio.to_thread`; it is thread-safe.
- **Carrying out what an agent recalled** (the usual pattern on leaving a place): `recall` there, let the agent pick items and classify each, then call `carry_out(ctx, text, type, source=item)` per item. The item's own label set is the source, because it may have been formed with different people present than now.
- **Writes that break a rule** raise `PermissionError` before anything is stored. Store errors raise `HindsightError`. None of these calls ever returns an unchecked result. Recall also applies memgate's own filter to whatever the store returns: an item whose label set the context may not read is dropped and counted in the recall's log line, even if a store without a second lock returned it.
- **Provenance** (optional; recommended where audit matters): `HindsightMemory(..., provenance=ProvenanceLog(root, gate))` from `memgate.provenance`. It keeps a W3C PROV-style record of every write, recall and turn, with one SQLite file per high-assurance location.

A turn, in order:
1. `recall(ctx, …)`.
2. The agent speaks.
3. `say(ctx, text, [batch.recall_id])`.
4. `remember(ctx, what was said, turns=[turn])`.

When the agent leaves, the host may call `carry_out` for whatever the agent chooses to take, then drops the agent's working context.

## Stores and capabilities (0.6.0)

memgate's decisions live in `memgate.core` and know nothing about the store; a store implements `memgate.store.Store` (`ensure`, `put`, `search`, `pending`) and declares `Capabilities`. `HindsightMemory` is `Memory` over the Hindsight store; `Memory(gate, Mem0Store(...), shared="ranch")` runs the same decisions over Mem0 (`memgate[mem0]`). What memgate guarantees with every store rests on its client-side decisions; the rest depends on the store:

| Capability | Hindsight | Mem0 | What it gives you |
| --- | --- | --- | --- |
| Second lock | yes (the validator inside the server) | no | Writes and recalls are checked again inside the store, whatever the client sent. Without it, a compromised host process could read anything |
| Idempotent replace | yes | emulated | `key=` makes a retried write replace its earlier self |
| Partitions | yes (a bank per high-assurance location) | no | High-assurance memories never share storage, ranking or consolidation with the rest; without it they are kept apart by label only |
| Delete | yes, with derived items | yes | `forget`, `forget_location` |
| List by label set | yes | yes | `personal`, `location`, conformance's `class-apart` |
| Stats | yes | partial | `stats`, `memgate inspect` |
| Consolidation control | yes (per partition) | nothing to control | a class's `consolidate: false` |

`memgate conformance` checks only what the store claims; the rest is reported as skipped with the reason. The proofs cover the decisions ([[memgate Proofs]] in the vault); the second lock and per-label-set consolidation are properties of Hindsight.

## Verify

1. `memgate check-world world.json`: the host's world file is usable.
2. `memgate conformance --url unix:/path/to/memgate.sock` (or an `http://` address), with the same `MEMGATE_*` settings as the server; add `--partition-url` for a split deployment. This plants canaries in a throwaway bank, checks every rule against the live deployment (validator present, witnesses, elsewhere, forged tags, write rules, carry-out, high assurance and its partition and seal, since 0.7.0 the source seal, since 0.8.0 the location's view and purge, and since 0.8.2 that an agent and location the world doesn't list are refused, which runs on any world, an empty one included), then deletes the bank. The source-seal checks hold one ordinary location by rewriting the world file (`MEMGATE_WORLD`, which conformance must be able to write and the server must follow): for a few seconds, carry-outs from that location are refused and what real agents carried out of it is withheld, then only that environment's `carry_out` is put back. Run it on an idle deployment, or let the checks skip by making the file read-only to conformance. It adapts to the host's world and skips checks the world has no place for. It exits non-zero on any failure. Run it after every deployment change.
3. **Host-level tests memgate can't do for you:**
   - an agent's Context changes when it moves;
   - participants match who is really present;
   - no agent process can read `MEMGATE_SECRET` or reach the store's port;
   - working context is cleared on leaving a high-assurance location.

## Stop and ask the owner before

- editing the Cedar policies (`src/memgate/policies/`) or the validator: the proofs and tests are the spec;
- letting any agent-facing code construct a `Context` from agent-supplied values;
- giving any agent process the secret, or exposing the memory store beyond the host;
- turning on Hindsight's reflect or mental models: both blend a whole bank, and the validator refuses them;
- disabling a failing conformance check.

## Limits (0.8.2)

- **Two memory systems:** Hindsight 0.10.1 (pinned; the only store with a second lock) and Mem0 2.2 (client-side enforcement only). Another store is a `Store` implementation.
- **Python:** 3.11 to 3.14 for the client (tested on 3.12 and 3.14 in CI); the server runs on 3.12, which Hindsight's stack is tested with.
- **Identity and context verification are the host's** (see the contract).
- **Not tested against adversarial agents.** The evidence covers cooperative agents.
- **Reflect and mental models are disabled** under memgate.
