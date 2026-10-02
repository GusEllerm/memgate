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
3. **The world file mirrors the host's world.** Every agent, location and environment the host uses must be listed before it is used. Unlisted ones are refused. Regenerate the file when the world changes. Write it to a temporary name and rename it, so memgate never reads a half-written file. memgate picks up changes within a second, with no restart.
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
    {"id": "severed-floor", "carry_out": []}
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
| Environment | A set of locations sharing one carry-out rule | Which memory types may leave: `carry_out` lists them. Omitted means all four; `[]` means nothing leaves |
| Location | Where conversations happen; every memory formed there is bound to it | Which locations exist, and which are high assurance |
| High assurance | Outbound only: nothing leaves, anything inside stays inside; personal memory may still be recalled there | Which locations need it (secrets, sensitive work) |
| Agent | An identity with its own personal memory | Every agent id the host will ever pass |
| Participants | Who is present in a conversation (the Context) | Taken from the simulation at the time of each call |

Ids are free strings, except that `--ha--` is reserved.

## Install and run

```sh
# the server side: memgate with the Hindsight version its validator is tested against (its own environment)
pip install "memgate[hindsight] @ git+https://github.com/GusEllerm/memgate@v0.4.3#subdirectory=memgate"
# the host side: the client only (cedarpy is its one dependency); add [async] for AsyncHindsightMemory (httpx)
pip install "memgate[async] @ git+https://github.com/GusEllerm/memgate@v0.4.3#subdirectory=memgate"

export MEMGATE_WORLD=/srv/host/world.json
export MEMGATE_REGISTRY=/srv/host/memgate/registry.sqlite     # label-set registry (SQLite), shared by both sides
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
- **Readiness:** don't detect startup from the server's log (at the default warning level uvicorn prints no "running on" line). Probe `GET /health` over the socket or port until it answers 200, or retry the client's `create_bank()` until it stops raising; the first request after start can take a while because the embedder loads.
- **The LLM** is used by Hindsight to extract and consolidate memories (any OpenAI-compatible endpoint). **Embeddings** are local (BAAI/bge-small-en-v1.5 by default).
- **The host process and the server must see the same three settings:** `MEMGATE_WORLD`, `MEMGATE_REGISTRY` and `MEMGATE_SECRET`.
- **The database:** `pg0://name` is an embedded Postgres. For your own server, use a `postgresql://` URL in `MEMGATE_DB`, not the `--db` flag, so the password stays out of the process list. Put the password in the user part (`postgresql://user:password@host/db`): memgate and Hindsight both mask it in their output. `memgate serve` refuses a password in the query (`?password=`), because Hindsight 0.10.1 logs the query in clear. Give memgate its own database role, with access to its database only, so the server can't reach the host's other data. The database needs the `vector` (pgvector) and `pg_trgm` extensions; pre-create them if Hindsight's role may not.
- **World changes:** both sides re-read the world file when it changes, checked at most every `MEMGATE_WORLD_CHECK_S` seconds (default 1; `memgate serve --world-check-interval`). In the host, call `gate.refresh(force=True)` right after writing the file. A memory call to something created within that interval may be refused by the server; retry once.
- **The registry** is a SQLite file (WAL). Any number of host processes may write it (for example several web workers), and the server only reads it. That works across processes and containers on one host. Never put it on NFS or EFS, or on a macOS Docker Desktop bind mount shared with a host process.
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
| `mem.carry_out(ctx, text, memory_type, source=None, source_writes=(), key=None)` | An agent takes something with it into personal memory | `source` is what the content was formed under. Pass the `Recalled` item itself to carry out something recalled (its label set, and its write for provenance), or a label set or its ID. It defaults to `ctx`'s conversation. It must be readable in `ctx`. Raises `PermissionError` if the environment forbids it |
| `mem.say(ctx, text, recalls=[recall_id, ...])` | An agent speaks | Records which recalls it drew on, so later memories trace back (needs a `ProvenanceLog`) |

- **Idempotent writes:** pass `key=` (any string the host chooses, e.g. its own segment id) to `remember`, `keep_note` or `carry_out`. The write id is derived from the key and the label set, so re-sending the same key under the same label set (same location, same participants; same author for a note) replaces the earlier write instead of storing it twice: Hindsight upserts by that id, and a byte-identical re-send extracts nothing new. A host that records at least once (an outbox drained after a crash) gets exactly-once storage this way. The id carries the label set, and the server refuses a write id minted under another label set, so a key can never reach another conversation's memory. An agent's personal memory (carry-outs) is one label set, so a carry-out key must be unique across everything that agent ever carries out, and a retry must re-send the same text under the same key (store the chosen items, then write them).
- **Async hosts:** `AsyncHindsightMemory` (same arguments, `await` every call; use `async with`, or call `aclose()`) has the same API and the same decisions. Otherwise wrap the sync client in `asyncio.to_thread`; it is thread-safe.
- **Carrying out what an agent recalled** (the usual pattern on leaving a place): `recall` there, let the agent pick items and classify each, then call `carry_out(ctx, text, type, source=item)` per item. The item's own label set is the source, because it may have been formed with different people present than now.
- **Writes that break a rule** raise `PermissionError` before anything is stored. Store errors raise `HindsightError`. None of these calls ever returns an unchecked result.
- **Provenance** (optional; recommended where audit matters): `HindsightMemory(..., provenance=ProvenanceLog(root, gate))` from `memgate.provenance`. It keeps a W3C PROV-style record of every write, recall and turn, with one SQLite file per high-assurance location.

A turn, in order:
1. `recall(ctx, …)`.
2. The agent speaks.
3. `say(ctx, text, [batch.recall_id])`.
4. `remember(ctx, what was said, turns=[turn])`.

When the agent leaves, the host may call `carry_out` for whatever the agent chooses to take, then drops the agent's working context.

## Verify

1. `memgate check-world world.json`: the host's world file is usable.
2. `memgate conformance --url unix:/path/to/memgate.sock` (or an `http://` address), with the same `MEMGATE_*` settings as the server; add `--partition-url` for a split deployment. This plants canaries in a throwaway bank, checks every rule against the live deployment (validator present, witnesses, elsewhere, forged tags, write rules, carry-out, high assurance and its partition and seal), then deletes the bank. It adapts to the host's world and skips checks the world has no place for. It exits non-zero on any failure. Run it after every deployment change.
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

## Limits (0.4.3)

- **One memory system:** Hindsight 0.10.1, pinned. Other stores need an adapter.
- **Identity and context verification are the host's** (see the contract).
- **Not tested against adversarial agents.** The evidence covers cooperative agents.
- **Reflect and mental models are disabled** under memgate.
