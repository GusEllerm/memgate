# memgate

Context-scoped permissions for agent memory. The current context (who is acting, where, who is
present) decides which memories an agent may recall, what it may carry into its personal memory,
and how memories are labelled. Policies are written in [Cedar](https://www.cedarpolicy.com) and
proved with Cedar's symbolic compiler (`proofs/`); memory systems plug in through adapters (today
Hindsight 0.10.1).

**Integrating it into a host application?** Read [INTEGRATION.md](INTEGRATION.md) first.

```sh
pip install "memgate[hindsight] @ git+https://github.com/GusEllerm/memgate@v0.7.0#subdirectory=memgate"

memgate check-world world.json          # is this world file usable?
memgate serve --port 8889               # Hindsight with memgate's validator (MEMGATE_WORLD/REGISTRY/SECRET set)
memgate conformance --url http://127.0.0.1:8889   # does the live deployment enforce every rule?
```

```python
from memgate import Context, Gate
from memgate.adapters.hindsight import HindsightMemory

mem = HindsightMemory(Gate.from_env(), bank="ranch", base_url="http://127.0.0.1:8889")
ctx = Context("ada", "lab", ("ada", "bo"))           # built by the host, from verified facts
mem.remember(ctx, "Bo said the lab safe combination is 4471.")
mem.recall(ctx, "lab safe combination")
```

A runnable walk-through is in [examples/quickstart.py](examples/quickstart.py).

## Development

```sh
uv sync && uv run pytest                                       # unit tests
MEMGATE_HINDSIGHT_URL=http://127.0.0.1:8889 MEMGATE_WORLD=.run/world.json \
  MEMGATE_REGISTRY=.run/registry.sqlite MEMGATE_SECRET=$(cat .run/secret) uv run pytest   # plus live tests
cd proofs && CVC5=/path/to/cvc5 cargo run --release            # formal proofs of the policies
```

The validator spec tests (`tests/test_validator.py`) need Hindsight installed. Design and evidence
are in the repo's vault (`docs/vault/`), starting from `Modules/memgate Core.md`.
