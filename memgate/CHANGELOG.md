# Changelog

## Unreleased

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
