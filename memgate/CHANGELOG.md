# Changelog

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
