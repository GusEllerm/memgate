# Changelog

## 0.4.3 (2026-10-02)

- `carry_out` takes `key=` like `remember` and `keep_note` (0.4.1): a retried carry-out replaces its earlier
  self in the agent's personal memory instead of adding a copy. The write ID is bound to the personal label
  set, which the validator's existing check already covers. Personal memory is one label set per agent, so a
  key must be unique across everything that agent carries out. For CHORUS's phase-3 departures.

## 0.4.2 (2026-10-01)

- **Security: Hindsight's log holds no recall queries.** Hindsight 0.10.1 logs the first 50 characters
  of every recall query at INFO, and the whole recall log at ERROR when a recall fails. A query is
  conversation text (a host typically recalls with the newest message), and inside a high-assurance
  location it is sealed text, written outside the partition. `memgate serve` now sets
  `HINDSIGHT_API_LOG_LEVEL=warning` (fingerprinted with its other forced settings, so a `.env` cannot
  raise it; `--hindsight-log-level` / `MEMGATE_HINDSIGHT_LOG_LEVEL` overrides it, with a warning that
  the log is then labelled data). The validator also installs a logging filter (`RedactQueries`) that
  removes the query from Hindsight's recall and reflect log lines at any level, so the ERROR path is
  covered too. Verified live: a recall's text never reaches the server's output at level info. Found
  by the CHORUS integration's phase-2 live run.

## 0.4.1 (2026-10-01)

- **Idempotent writes.** `remember` and `keep_note` take `key=`: the write ID is derived from the key
  and the label set (`w_<label set>_<hash>`), so a write re-sent with the same key under the same
  label set replaces its earlier self (Hindsight upserts by document_id, and a byte-identical re-send
  extracts nothing new) instead of storing a second copy. The provenance log replaces the write's row
  and sources too. A host that delivers at least once (an outbox drained after a crash) gets
  exactly-once storage. Every write ID, keyed or not, now carries its label set.
- **Security (validator):** `validate_retain` refuses any `update_mode` (an append would fold another
  document's text into this write and re-extract it under this write's label set) and any
  `document_id` not minted under the item's own label set (a reused ID would replace, and so erase,
  another label set's document). Neither was reachable before 0.4.1, since only memgate's clients
  hold the secret and never sent either; with caller keys the check matters. Found by the CHORUS
  integration's review of its phase-2 plan.

## 0.4.0 (2026-09-30)

- **Unix-socket transport** (security: the server proves who it is). `memgate serve --socket PATH`
  serves Hindsight on a Unix socket (Hindsight's ASGI app under uvicorn `--uds`; no TCP port). Clients
  and `memgate conformance` take the address `unix:PATH`. Before every request over a socket, the
  client checks the socket's directory is private (0700) and owned by this user, so nothing else can
  be listening to collect the shared secret. Over a port, a process that binds it first could.
  `serve` creates the directory private and refuses one that isn't. The async client uses httpx's
  socket transport. Live: conformance passes over a socket. Requested by the CHORUS integration's
  review.

- **Security:** the clients and `memgate conformance` never send a request through a proxy. urllib
  honours `HTTP_PROXY` from the environment, and a proxy would see the shared secret in the request
  header. The sync client uses a proxy-free opener, and the async client sets `trust_env=False`.
  Reported by the CHORUS integration's review.

## 0.3.2 (2026-09-30)

- **Security:** Hindsight loads the first `.env` it finds walking up from its working directory, with
  `override=True`, so a stray or planted `.env` could drop memgate's validator, change the database or
  turn traces on. `memgate serve` now starts Hindsight in a private directory (`--workdir`, default
  `.memgate-serve` beside the registry, 0700) holding an empty `.env` (0600), and refuses to start if
  it isn't empty. It also passes a fingerprint of every setting it forces
  (`MEMGATE_SERVE_FINGERPRINT`); the validator checks it once Hindsight has loaded and refuses to load
  if anything changed, which stops Hindsight from starting. Verified live: a hostile `.env` where
  `serve` is run, and above its working directory, leaves the validator loaded and the real secret in
  force. Launched directly from the same directory, Hindsight ran without the validator. Reported by
  the CHORUS integration's review.
- Never start Hindsight with `hindsight-api` directly under memgate; always use `memgate serve`.

## 0.3.1 (2026-09-30)

- **Security:** `memgate serve` redacts the database URL it prints at startup: a password in the
  user part or in the query is shown as `***`. 0.2.0 printed the full URL, and 0.3.0 still printed a
  password given as a query parameter. Hindsight still receives the real URL.
- **Security:** `memgate serve` refuses a database URL with a password in its query (`?password=`,
  `sslpassword=` and similar). Hindsight 0.10.1 masks a password in the URL's user part but logs the
  query in clear at startup, so put the password in the user part. Checked end to end: with the
  password in the user part, it appears nowhere in memgate's or Hindsight's output, including when
  the database can't be reached (`tests/test_serve_logs.py`).
- If you ran 0.2.0 or 0.3.0 with a password in `MEMGATE_DB`, redact the logs and rotate the password.
  Reported by the CHORUS integration.
- **Registry:** an explicit 30 s lock wait (`Registry(path, timeout=30.0)`), and a test that several
  processes can write one registry at once (for example web workers).

## 0.3.0 (2026-09-30)

Changes for the Knowledge Ranch integration.

- **Carry out what was recalled:** `carry_out(ctx, text, type, source=<Recalled>)` takes the recalled
  item's own label set as the source, and its write as provenance. `source` also accepts a label set
  or its ID; it still defaults to the Context's conversation.
- **Async client:** `AsyncHindsightMemory`, the same API with `await` (`pip install 'memgate[async]'`,
  httpx). Both clients share one core that makes every decision and does no I/O.
- **A separate server for high-assurance partitions:** the client's `partition_url=` sends partition
  banks to their own server. `memgate serve --scope shared|partitions|all` makes each server's
  validator refuse the other's banks. `memgate conformance --partition-url` checks a split deployment
  (a new `split-scope` check).
- **World check interval:** `MEMGATE_WORLD_CHECK_S` / `memgate serve --world-check-interval` (default
  1 s; 0 means on every decision).
- `memgate serve` no longer prints a database password.

## 0.2.0 (2026-09-30)

First release meant for integration into a host application.

- **API:** every `HindsightMemory` call takes a `Context` (agent, location, participants), built by the
  host from verified facts. A carry-out's source defaults to the Context's conversation. Package
  exports: `memgate.Context`, `memgate.Gate`, `memgate.adapters.hindsight.HindsightMemory`.
- **Writes decided in Cedar:** a `write` action with the high-assurance write seal (anything
  written in a high-assurance location stays there). Carry-out is allowed only where its source is
  readable. Proved with SymCC (`proofs/`, 31 properties).
- **High-assurance partitions:** one Hindsight bank per high-assurance location, enforced by the
  client and the validator.
- **Fail closed:** unknown agents or locations are refused everything.
- **World reload:** `Gate` follows the world file without a restart. An unreadable file keeps the
  last good world.
- **CLI:** `memgate serve` (Hindsight with the validator, loopback only), `memgate check-world`,
  `memgate conformance` (canary checks against a live deployment), `memgate secret`.
- **Integration:** `INTEGRATION.md`, the `integrate-memgate` skill (the repo's Claude Code plugin),
  and `examples/quickstart.py`.
- **Breaking:** the client's methods now take a `Context` instead of separate agent, location and
  participant arguments.

## 0.1.0 (2026-09-29)

Labels, registry, Cedar read and carry-out policies with the SQL residual compiler, derivation,
provenance, and the Hindsight client and validator.
