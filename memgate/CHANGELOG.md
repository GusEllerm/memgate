# Changelog

## 0.3.1 (2026-09-30)

- **Security:** `memgate serve` redacts the database URL it prints at startup: a password in the
  user part or in the query (`password=`, `sslpassword=` and similar) is shown as `***`. 0.2.0 printed
  the full URL, and 0.3.0 still printed a password given as a query parameter. Hindsight still
  receives the real URL. If you ran 0.2.0 with a password in `MEMGATE_DB`, redact your logs and
  consider rotating the password. Reported by the CHORUS integration.
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
