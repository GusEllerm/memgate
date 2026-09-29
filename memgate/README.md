# memgate

Permission layer for agent memory (working name). The current context (who is acting, where, who was present) decides which memories an agent may recall, what it may carry into its personal memory, and how derived memories are labelled. Policies are written in [Cedar](https://www.cedarpolicy.com); memory systems plug in through adapters.

Design: `docs/vault/Concepts/Permission Layer.md` in this repository.

```sh
uv sync
uv run pytest
```
