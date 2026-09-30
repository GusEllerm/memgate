# memgate

Context-scoped permissions for agent memory. What an agent may recall, store and carry into its
personal memory is decided by its context: who it is, where it is, and who else is present. Policies
are written in [Cedar](https://www.cedarpolicy.com) and formally proved; memgate sits in front of a
memory system (today [Hindsight](https://github.com/vectorize-io/hindsight)) and enforces the rules
on both sides of it.

| You want to | Go to |
| --- | --- |
| **Integrate memgate into a host application** | [`memgate/INTEGRATION.md`](memgate/INTEGRATION.md), or the `integrate-memgate` skill: `claude plugin marketplace add GusEllerm/memgate`, then `claude plugin install memgate@memgate` |
| Use the library and CLI | [`memgate/`](memgate/) (`memgate serve`, `check-world`, `conformance`) |
| Understand the design and the evidence | the Obsidian vault at [`docs/vault/`](docs/vault/Home.md) (open it with "Open folder as vault"), kept in sync with the code by [livedocs](https://github.com/GusEllerm/vault-drift) |
| Run the benchmarks | [`benchmark/`](benchmark/): LoCoMo and the selective-memory benchmark (to be split out at publication) |

The repo was called agentic-memory until 2026-09-30.
