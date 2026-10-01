"""Conformance: prove a live memgate deployment enforces the rules, end to end.

    memgate conformance --url http://127.0.0.1:8889        # MEMGATE_WORLD, MEMGATE_REGISTRY, MEMGATE_SECRET set
    memgate conformance --url http://127.0.0.1:8889 --partition-url http://127.0.0.1:8890   # split deployment

Run it against the deployment's own server and world, after any change to the deployment. It picks
agents and locations from the world, plants canary strings (unique codes) in a throwaway bank,
checks who can recall each from where, probes the validator directly, then deletes the bank. Checks
that need something the world doesn't have (a second location, a high-assurance location, an
environment that refuses a carry-out) are reported as skipped. Costs a few dozen LLM calls, for
Hindsight's extraction of the canary memories.

Exit code 0 means every applicable check passed.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass

from memgate.context import HEADER_AGENT, HEADER_LOCATION, HEADER_ROLE, HEADER_SECRET, Context, Gate, partition_bank
from memgate.derivation import personal_labels
from memgate.world import MEMORY_TYPES


@dataclass
class Check:
    id: str
    claim: str
    status: str = "skip"         # pass | fail | skip
    detail: str = ""


def _raw(url: str, method: str, path: str, body: dict | None, headers: dict) -> tuple[int, str]:
    req = urllib.request.Request(f"{url}{path}", method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=300) as r:   # never via a proxy
            return r.status, r.read().decode(errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace")


def run(gate: Gate, url: str, wait_s: float = 900, partition_url: str | None = None) -> list[Check]:
    from memgate.adapters.hindsight.client import HindsightError, HindsightMemory

    url = url.rstrip("/")
    w = gate.world
    checks: dict[str, Check] = {c.id: c for c in [
        Check("secret", "A request without memgate's secret is refused (the validator is loaded and keyed)"),
        Check("side-doors", "Reflect, memory listing and document reads are refused to agents"),
        Check("witness", "A participant recalls a conversation in its location"),
        Check("non-witness", "An agent who wasn't there cannot recall it, even in the same location"),
        Check("elsewhere", "A participant cannot recall it from another location"),
        Check("forged-tags", "A recall asking for a label set the caller may not read gets nothing from it"),
        Check("write-rules", "The validator refuses a write under a label set the writer may not write"),
        Check("carry-out", "A permitted carry-out becomes personal memory: its owner recalls it elsewhere, no one else does"),
        Check("carry-refused", "A carry-out the environment forbids is refused and stores nothing"),
        Check("ha-inside", "A high-assurance conversation is recalled inside its location"),
        Check("ha-outside", "...and never outside it"),
        Check("ha-partition", "It is stored in the location's own partition, not the shared bank"),
        Check("ha-partition-search", "The partition cannot be searched from outside"),
        Check("ha-seal", "Personal memory cannot be written inside a high-assurance location"),
        Check("split-scope", "In a split deployment, each server refuses the other's banks"),
    ]}

    def ok(cid, cond, detail=""):
        checks[cid].status, checks[cid].detail = ("pass" if cond else "fail"), detail

    ordinary = sorted(l for l in w.locations if not w.high_assurance(l))
    ha = sorted(l for l in w.locations if w.high_assurance(l))
    agents = sorted(w.agents)
    bank = f"memgate-conformance-{uuid.uuid4().hex[:8]}"
    mem = HindsightMemory(gate, bank=bank, base_url=url, partition_url=partition_url)
    purl = (partition_url or url).rstrip("/")
    admin = {HEADER_SECRET: gate.secret, HEADER_ROLE: "admin"}

    def as_(agent, loc):
        return {HEADER_SECRET: gate.secret, HEADER_AGENT: agent, HEADER_LOCATION: loc}

    try:
        mem.create_bank()
        status, _ = _raw(url, "POST", f"/v1/default/banks/{bank}/memories/recall", {"query": "x"}, {})
        ok("secret", status == 403, f"status {status}")
        if len(agents) < 3 or not ordinary:
            for c in checks.values():
                if c.status == "skip":
                    c.detail = "the world needs at least three agents and one ordinary location"
            return list(checks.values())

        a, b, c = agents[:3]
        l1 = ordinary[0]
        l2 = ordinary[1] if len(ordinary) > 1 else None
        codes = {k: f"MGC-{k.upper()}-{uuid.uuid4().hex[:6]}" for k in ("conv", "carry", "refused", "ha")}
        here = Context(a, l1, (a, b))
        mem.remember(here, f"{a} and {b} agreed the conformance canary for {l1} is {codes['conv']}.")

        carry_type = next((t for t in sorted(w.carry_out_types(frozenset({l1})))), None)
        if carry_type:
            mem.carry_out(here, f"{a}'s own {carry_type}: the conformance keepsake code is {codes['carry']}.", carry_type)
        refusing = next(((l, t) for l in ordinary for t in sorted(MEMORY_TYPES - w.carry_out_types(frozenset({l})))), None)
        if ha:
            v = ha[0]
            mem.remember(Context(a, v, (a, b)), f"Inside {v}, {a} and {b} set the conformance dial to {codes['ha']}.")

        deadline = time.time() + wait_s
        while mem.pending_operations() and time.time() < deadline:
            time.sleep(5)

        def sees(agent, loc, code, query="conformance canary code"):
            return any(code in r.text for r in mem.recall(Context(agent, loc), query, k=20))

        s1, _ = _raw(url, "POST", f"/v1/default/banks/{bank}/reflect", {"query": "anything"}, as_(a, l1))
        s2, _ = _raw(url, "GET", f"/v1/default/banks/{bank}/memories/list", None, as_(a, l1))
        s3, _ = _raw(url, "GET", f"/v1/default/banks/{bank}/documents", None, as_(a, l1))
        ok("side-doors", {s1, s2, s3} == {403}, f"reflect {s1}, list {s2}, documents {s3}")

        ok("witness", sees(a, l1, codes["conv"]))
        ok("non-witness", not sees(c, l1, codes["conv"]))
        if l2:
            ok("elsewhere", not sees(a, l2, codes["conv"]))
        else:
            checks["elsewhere"].detail = "the world has only one ordinary location"

        conv_ls = gate.registry.register(here.conversation())
        status, body = _raw(url, "POST", f"/v1/default/banks/{bank}/memories/recall",
                            {"query": "conformance canary code", "tags": [conv_ls], "tags_match": "any"}, as_(c, l1))
        ok("forged-tags", status == 200 and codes["conv"] not in body, f"status {status}")
        status, _ = _raw(url, "POST", f"/v1/default/banks/{bank}/memories",
                         {"items": [{"content": "misplaced", "tags": [conv_ls]}]}, as_(c, l1))
        ok("write-rules", status == 403, f"status {status}")

        if carry_type and l2:
            ok("carry-out", sees(a, l2, codes["carry"], "conformance keepsake code") and
               not sees(b, l2, codes["carry"], "conformance keepsake code"), f"type {carry_type}")
        else:
            checks["carry-out"].detail = "no ordinary location lets any memory type out, or only one location"
        if refusing:
            loc, t = refusing
            try:
                mem.carry_out(Context(a, loc, (a, b)), f"forbidden {codes['refused']}", t)
                ok("carry-refused", False, f"{t} out of {loc} was allowed")
            except PermissionError:
                ok("carry-refused", True, f"{t} out of {loc}")
        else:
            checks["carry-refused"].detail = "every ordinary location lets every memory type out"

        if ha:
            ok("ha-inside", sees(a, v, codes["ha"], "conformance dial"))
            ok("ha-outside", not sees(a, l1, codes["ha"], "conformance dial"))
            vault_bank = partition_bank(bank, v)
            docs = lambda bk: json.loads(_raw(purl if bk == vault_bank else url, "GET",
                                              f"/v1/default/banks/{bk}/documents?limit=500", None, admin)[1] or "{}").get("items", [])
            reg = gate.registry.all()
            in_v = lambda d: v in reg[d["tags"][0]].locs
            ok("ha-partition", any(in_v(d) for d in docs(vault_bank)) and not any(in_v(d) for d in docs(bank)))
            status, _ = _raw(purl, "POST", f"/v1/default/banks/{vault_bank}/memories/recall", {"query": "x"}, as_(a, l1))
            ok("ha-partition-search", status == 403, f"status {status}")
            mine = gate.registry.register(personal_labels(a))
            status, _ = _raw(url, "POST", f"/v1/default/banks/{bank}/memories",
                             {"items": [{"content": "sealed", "tags": [mine]}]}, as_(a, v))
            try:
                mem.carry_out(Context(a, v), "sealed", "opinion", source=personal_labels(a))
                client_refused = False
            except PermissionError:
                client_refused = True
            ok("ha-seal", status == 403 and client_refused, f"validator {status}, client refused {client_refused}")
            if partition_url:
                s1, _ = _raw(url, "POST", f"/v1/default/banks/{vault_bank}/memories/recall", {"query": "x"}, as_(a, v))
                s2, _ = _raw(purl, "POST", f"/v1/default/banks/{bank}/memories/recall", {"query": "x"}, as_(a, l1))
                ok("split-scope", s1 == 403 and s2 == 403, f"shared server on a partition {s1}, partition server on shared {s2}")
            else:
                checks["split-scope"].detail = "not a split deployment (no --partition-url)"
        else:
            for cid in ("ha-inside", "ha-outside", "ha-partition", "ha-partition-search", "ha-seal", "split-scope"):
                checks[cid].detail = "the world has no high-assurance location"
    finally:
        for bk in mem.partitions():
            try:
                mem._call("DELETE", f"/v1/default/banks/{bk}", None, role="admin")
            except (HindsightError, OSError):
                pass
    return list(checks.values())


def report(checks: list[Check]) -> str:
    mark = {"pass": "PASS", "fail": "FAIL", "skip": "skip"}
    lines = [f"{mark[c.status]:4}  {c.id:20} {c.claim}" + (f"  [{c.detail}]" if c.detail else "") for c in checks]
    n = {s: sum(c.status == s for c in checks) for s in ("pass", "fail", "skip")}
    lines.append(f"\n{n['pass']} passed, {n['fail']} failed, {n['skip']} skipped")
    return "\n".join(lines)
