"""memgate end to end, against a running `memgate serve`.

    export MEMGATE_WORLD=examples/world.json MEMGATE_REGISTRY=/tmp/memgate-example/registry.sqlite
    export MEMGATE_SECRET=$(memgate secret)
    memgate serve --db pg0://memgate-example &          # Hindsight with memgate's validator, port 8889
    python examples/quickstart.py

Every call takes a Context: who is acting, where, and who is present. In a real host the Context is
built by the host from what it has verified, never by the agent (see INTEGRATION.md).
"""

import os
import time

from memgate import Context, Gate
from memgate.adapters.hindsight import HindsightMemory

gate = Gate.from_env()
mem = HindsightMemory(gate, bank="quickstart", base_url=os.environ.get("MEMGATE_URL", "http://127.0.0.1:8889"))
mem.create_bank()

in_lab = Context("ada", "lab", ("ada", "bo"))                   # Ada and Bo talking in the lab
mem.remember(in_lab, "Bo told Ada the lab safe combination is 4471.")
mem.carry_out(in_lab, "Ada thinks the lab espresso machine is excellent.", "opinion")   # campus lets it out

try:
    mem.carry_out(Context("ada", "gallery", ("ada", "bo")), "The gallery alarm code is 9902.", "fact")
except PermissionError as e:
    print("refused, as it should be:", e)                      # the studio lets out opinions and skills only

mem.remember(Context("ada", "vault", ("ada", "bo")), "Inside the vault the dial was set to 7.")
try:
    mem.carry_out(Context("ada", "vault", ("ada", "bo")), "The vault dial is 7.", "fact")
except PermissionError as e:
    print("refused, as it should be:", e)                      # nothing leaves a high-assurance location

while mem.pending_operations():                                # Hindsight extracts memories in the background
    time.sleep(3)

def show(ctx, query):
    print(f"{ctx.agent} in {ctx.location}, asking {query!r}:", [m.text for m in mem.recall(ctx, query, k=5)] or "nothing")

show(Context("ada", "lab"), "lab safe combination")             # a participant, here: yes
show(Context("cy", "lab"), "lab safe combination")              # wasn't there: nothing
show(Context("ada", "cafe"), "lab safe combination")            # somewhere else: nothing
show(Context("ada", "cafe"), "espresso machine")                # carried-out opinion: travels with Ada
show(Context("ada", "vault"), "vault dial")                     # inside the vault: yes
show(Context("ada", "lab"), "vault dial")                       # outside it: nothing
