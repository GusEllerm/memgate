"""Conformance: prove a live memgate deployment enforces the rules, end to end.

    memgate conformance --url http://127.0.0.1:8889        # MEMGATE_WORLD, MEMGATE_REGISTRY, MEMGATE_SECRET set
    memgate conformance --url http://127.0.0.1:8889 --partition-url http://127.0.0.1:8890   # split deployment

Run it against the deployment's own server and world, after any change to the deployment. It picks
agents and locations from the world, plants canary strings (unique codes) in a throwaway partition,
checks who can recall each from where, probes the store's second lock directly where it has one, then
deletes the partition. Checks that need something the world doesn't have (a second location, a
high-assurance location, an environment that refuses a carry-out) are reported as skipped, and so are
checks that need a capability the store doesn't claim (memgate.store.Capabilities): a store without a
second lock skips the validator probes, one without partitions skips the partition checks. Costs a few
dozen LLM calls, for the store's extraction and consolidation of the canary memories. On a store without
partitions the canaries share the one collection with real data (label-set ids are content-addressed),
so cleanup deletes exactly the writes the run made; a store's own history may still hold their text.

The class checks keep a named item in an agent's personal set and its nameless version in the
"unattributed" class set, wait for consolidation, then list what the store holds: no derived item may
be built from another label set, and the planted name may appear in no item of the class set. That is
the separation the class exists for, which the store's per-label-set consolidation keeps (outside the
policies' proofs), so it is checked here rather than proved.

Exit code 0 means every applicable check passed.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass

from memgate.context import (HEADER_AGENT, HEADER_LOCATION, HEADER_ROLE, HEADER_SECRET, HEADER_VERSION, Context, Gate,
                             partition_bank)
from memgate.core import Memory
from memgate.derivation import personal_labels
from memgate.labels import CLASSES
from memgate.provenance import write_id_label_set
from memgate.world import MEMORY_TYPES

UNATTRIBUTED = CLASSES[0]

CLAIMS = [
    ("secret", "A request without memgate's secret is refused (the validator is loaded and keyed)"),
    ("side-doors", "Reflect, memory listing and document reads are refused to agents"),
    ("witness", "A participant recalls a conversation in its location"),
    ("non-witness", "An agent who wasn't there cannot recall it, even in the same location"),
    ("elsewhere", "A participant cannot recall it from another location"),
    ("forged-tags", "A recall asking for a label set the caller may not read gets nothing from it"),
    ("write-rules", "The validator refuses a write under a label set the writer may not write"),
    ("carry-out", "A permitted carry-out becomes personal memory: its owner recalls it elsewhere, no one else does"),
    ("carry-refused", "A carry-out the environment forbids is refused and stores nothing"),
    ("class-carry-out", "A carry-out into a class set: its owner recalls it elsewhere, no one else does"),
    ("class-downgrade", "Content from a class set cannot be carried into a less strict personal set"),
    ("class-minimum", "An environment's minimum class refuses a carry-out without it"),
    ("class-apart", "Consolidation never builds on another label set: the class set never gets the named item's name"),
    ("held-withheld", "Once a location's environment lets nothing out, what was carried out of it is recalled only there, and comes back when it is released"),
    ("held-derived", "What the store derived from a withheld item is withheld with it"),
    ("owner-view", "An agent's personal items can be listed, and only its own; forget removes one and nothing else"),
    ("class-legacy", "A class item kept in the shared partition before the class stopped consolidating is still listed and forgotten"),
    ("ha-inside", "A high-assurance conversation is recalled inside its location"),
    ("ha-outside", "...and never outside it"),
    ("ha-partition", "It is stored in the location's own partition, not the shared one"),
    ("ha-partition-search", "The partition cannot be searched from outside"),
    ("ha-seal", "Personal memory cannot be written inside a high-assurance location"),
    ("split-scope", "In a split deployment, each server refuses the other's banks"),
    ("location-view", "A location's conversation memory is listed with its participants, notes excluded; forgetting the location removes it all, notes included, and a participant recalls nothing of it afterwards"),
]
SECOND_LOCK_CHECKS = ("secret", "side-doors", "forged-tags", "write-rules", "ha-partition-search")


@dataclass
class Check:
    id: str
    claim: str
    status: str = "skip"         # pass | fail | skip
    detail: str = ""


def _raw(url: str, method: str, path: str, body: dict | None, headers: dict) -> tuple[int, str]:
    """A request straight at the server, as a probe of the second lock; it carries this release's version
    like the client does, so a server with a minimum client version judges the probe on its merits."""
    from memgate import __version__
    from memgate.adapters.hindsight.store import send      # http or unix, never via a proxy
    status, raw = send(url, method, path, json.dumps(body).encode() if body is not None else None,
                       {"Content-Type": "application/json", HEADER_VERSION: __version__, **headers}, 300)
    return status, raw.decode(errors="replace")


def _apart(mem: Memory, partition: str, label_sets: list[str], class_set: str, name: str) -> tuple[bool | None, str]:
    """(passed, detail) for class-apart, or (None, why) when the store derived nothing to check. Lists every
    label set conformance wrote to; a derived item's sources are write IDs, whose label set is in the ID."""
    items = []
    for ls in label_sets:
        items += mem.store.list(mem.core.partition_for(mem.gate.registry.get(ls)), ls)
    derived = [i for i in items if i.kind == "derived"]
    # A source the listing could not resolve to a write of the same label set was built from another set
    # (or from something since deleted): counted as crossed, never excused.
    crossed = [i for i in derived if any(write_id_label_set(s) != i.label_set for s in i.sources)]
    named = [i for i in items if i.label_set == class_set and name.lower() in i.text.lower()]
    if named:
        return False, f"{len(named)} class-set item(s) hold the name planted only in the plain set"
    if not derived:
        return None, f"the store derived nothing within the wait ({len(items)} items; the name appears nowhere in the class set)"
    in_class = sum(1 for i in derived if i.label_set == class_set)
    return (not crossed,
            f"{len(derived)} derived items ({in_class} in the class set): {len(crossed)} built across label sets or from "
            f"unresolved sources, 0 class-set items with the name")


def run(gate: Gate, url: str | None = None, wait_s: float = 900, partition_url: str | None = None,
        memory: Memory | None = None) -> list[Check]:
    """Check a deployment. Give `url` (a memgate serve address) for Hindsight, or any `memory` (a `Memory`
    over some store); with a store that has no second lock, the validator probes are skipped."""
    from memgate.adapters.hindsight.client import HindsightError, HindsightMemory

    if memory is None and not url:
        raise ValueError("give url (a memgate serve address) or memory (a Memory over some store)")
    w = gate.world
    checks: dict[str, Check] = {cid: Check(cid, claim) for cid, claim in CLAIMS}

    def ok(cid, cond, detail=""):
        checks[cid].status, checks[cid].detail = ("pass" if cond else "fail"), detail

    def skip(cid, why):
        checks[cid].detail = why

    ordinary = sorted(l for l in w.locations if not w.high_assurance(l))
    ha = sorted(l for l in w.locations if w.high_assurance(l))
    agents = sorted(w.agents)
    bank = f"memgate-conformance-{uuid.uuid4().hex[:8]}"
    if memory is None:
        url = (url or "").rstrip("/")
        mem = HindsightMemory(gate, bank=bank, base_url=url, partition_url=partition_url)
    else:
        # The caller's Memory is left alone: a fresh one over the same store, with the throwaway partition
        # name and no provenance, so the canaries record nothing in the host's provenance log.
        mem = Memory(memory.gate, memory.store, bank)
    caps = mem.capabilities
    hindsight = isinstance(mem, HindsightMemory)
    purl = (partition_url or url or "").rstrip("/")
    admin = {HEADER_SECRET: gate.secret, HEADER_ROLE: "admin"}
    created: list[str] = []              # every write id this run makes, for a cleanup that touches nothing else

    def as_(agent, loc):
        return {HEADER_SECRET: gate.secret, HEADER_AGENT: agent, HEADER_LOCATION: loc}

    probes = caps.second_lock and hindsight
    if not caps.second_lock:
        for cid in SECOND_LOCK_CHECKS:
            skip(cid, "the store has no second lock (memgate's client is the only enforcement)")
    elif not hindsight:
        for cid in SECOND_LOCK_CHECKS:
            skip(cid, "conformance can only probe Hindsight's validator directly")
    def keep(write_id: str) -> str:
        created.append(write_id)
        return write_id

    try:
        mem.create_bank()
        if probes:
            status, _ = _raw(url, "POST", f"/v1/default/banks/{bank}/memories/recall", {"query": "x"}, {})
            ok("secret", status == 403, f"status {status}")
        if len(agents) < 3 or not ordinary:
            for c in checks.values():
                if c.status == "skip" and not c.detail:
                    c.detail = "the world needs at least three agents and one ordinary location"
            return list(checks.values())

        a, b, c = agents[:3]
        l1 = ordinary[0]
        l2 = ordinary[1] if len(ordinary) > 1 else None
        codes = {k: f"MGC-{k.upper()}-{uuid.uuid4().hex[:6]}" for k in ("conv", "carry", "refused", "ha", "class", "legacy")}
        here = Context(a, l1, (a, b))
        conv_id = keep(mem.remember(here, f"{a} and {b} agreed the conformance canary for {l1} is {codes['conv']}."))
        written = [here.conversation().id]

        carry_type = next((t for t in sorted(w.carry_out_types(frozenset({l1})))), None)
        floor = w.min_class({l1})                          # meet the location's minimum, if its environment sets one
        canary_name = f"Zorvath{uuid.uuid4().hex[:4]}"
        kept_id = None
        if carry_type:
            kept_id = keep(mem.carry_out(here, f"{a}'s own {carry_type}: the conformance keepsake code is {codes['carry']}.", carry_type, cls=floor))
            written.append(personal_labels(a, floor, src=l1).id)
            # The same fact twice, once with a name in the plain personal set and once without in the class set.
            # A canary name, so that finding it in the class set can only mean the two sets were mixed.
            topic = f"the conformance buffer drifts above {codes['class']} degrees"
            if floor is None:
                keep(mem.carry_out(here, f"{canary_name} says {topic}.", carry_type))
            keep(mem.carry_out(here, f"A colleague says {topic}.", carry_type, cls=UNATTRIBUTED))
            written.append(personal_labels(a, UNATTRIBUTED, src=l1).id)
        refusing = next(((l, t) for l in ordinary for t in sorted(MEMORY_TYPES - w.carry_out_types(frozenset({l})))), None)
        if ha:
            v = ha[0]
            keep(mem.remember(Context(a, v, (a, b)), f"Inside {v}, {a} and {b} set the conformance dial to {codes['ha']}."))

        deadline = time.time() + wait_s
        while mem.pending_operations() and time.time() < deadline:
            time.sleep(5)

        def sees(agent, loc, code, query="conformance canary code"):
            return any(code in r.text for r in mem.recall(Context(agent, loc), query, k=20))

        if probes:
            s1, _ = _raw(url, "POST", f"/v1/default/banks/{bank}/reflect", {"query": "anything"}, as_(a, l1))
            s2, _ = _raw(url, "GET", f"/v1/default/banks/{bank}/memories/list", None, as_(a, l1))
            s3, _ = _raw(url, "GET", f"/v1/default/banks/{bank}/documents", None, as_(a, l1))
            ok("side-doors", {s1, s2, s3} == {403}, f"reflect {s1}, list {s2}, documents {s3}")

        ok("witness", sees(a, l1, codes["conv"]))
        ok("non-witness", not sees(c, l1, codes["conv"]))
        if l2:
            ok("elsewhere", not sees(a, l2, codes["conv"]))
        else:
            skip("elsewhere", "the world has only one ordinary location")

        conv_ls = gate.registry.register(here.conversation())
        if probes:
            status, body = _raw(url, "POST", f"/v1/default/banks/{bank}/memories/recall",
                                {"query": "conformance canary code", "tags": [conv_ls], "tags_match": "any"}, as_(c, l1))
            ok("forged-tags", status == 200 and codes["conv"] not in body, f"status {status}")
            status, _ = _raw(url, "POST", f"/v1/default/banks/{bank}/memories",
                             {"items": [{"content": "misplaced", "tags": [conv_ls]}]}, as_(c, l1))
            ok("write-rules", status == 403, f"status {status}")

        if carry_type and l2:
            ok("carry-out", sees(a, l2, codes["carry"], "conformance keepsake code") and
               not sees(b, l2, codes["carry"], "conformance keepsake code"), f"type {carry_type}" + (f", class {floor}" if floor else ""))
            ok("class-carry-out", sees(a, l2, codes["class"], "conformance buffer drift") and
               not sees(b, l2, codes["class"], "conformance buffer drift"), f"type {carry_type}")
        else:
            for cid in ("carry-out", "class-carry-out"):
                skip(cid, "no ordinary location lets any memory type out, or only one location")
        if carry_type:
            try:
                mem.carry_out(Context(a, l1), "downgraded", carry_type, source=personal_labels(a, UNATTRIBUTED, src=l1), cls=None)
                ok("class-downgrade", False, f"a {UNATTRIBUTED} item was carried into {a}'s plain personal set")
            except PermissionError as e:
                ok("class-downgrade", True, str(e))
        else:
            skip("class-downgrade", "no ordinary location lets any memory type out")
        floored = next(((l, t) for l in ordinary if w.min_class({l}) for t in sorted(w.carry_out_types(frozenset({l})))), None)
        if floored:
            loc, t = floored
            try:
                mem.carry_out(Context(a, loc, (a, b)), "no class given", t)
                ok("class-minimum", False, f"{t} out of {loc} without a class was allowed")
            except PermissionError as e:
                ok("class-minimum", True, str(e))
        else:
            skip("class-minimum", "no environment in the world sets a min_class")
        if not caps.list_by_label_set:
            skip("class-apart", "the store cannot list by label set")
        elif carry_type and floor is None:
            passed, detail = _apart(mem, bank, written, personal_labels(a, UNATTRIBUTED, src=l1).id, canary_name)
            if passed is None:
                skip("class-apart", detail)
            else:
                ok("class-apart", passed, detail)
        else:
            skip("class-apart", "no ordinary location lets any memory type out" if not carry_type else
                 f"{l1} sets a min_class, so the named item can't be kept there")
        if refusing:
            loc, t = refusing
            try:
                mem.carry_out(Context(a, loc, (a, b)), f"forbidden {codes['refused']}", t)
                ok("carry-refused", False, f"{t} out of {loc} was allowed")
            except PermissionError:
                ok("carry-refused", True, f"{t} out of {loc}")
        else:
            skip("carry-refused", "every ordinary location lets every memory type out")

        # The source seal (before owner-view forgets the keepsake): hold l1's environment in the world file and watch the keepsake disappear outside l1.
        flip = gate.world_path if gate.world_path and os.access(gate.world_path, os.W_OK) else None
        if not carry_type or not l2:
            skip("held-withheld", "no ordinary location lets any memory type out, or only one location")
            skip("held-derived", "no ordinary location lets any memory type out, or only one location")
        elif flip is None:
            skip("held-withheld", "conformance cannot write the world file to hold a location (MEMGATE_WORLD not writable)")
            skip("held-derived", "conformance cannot write the world file to hold a location (MEMGATE_WORLD not writable)")
        else:
            env_id = w.locations[l1].environment
            tmp = flip.with_suffix(flip.suffix + ".memgate-conformance")

            def set_hold(value):
                """Rewrite only l1's environment's carry_out in the live world file (re-read, so a host edit made
                meanwhile survives), atomically, as the guide asks hosts to write it."""
                spec = json.loads(flip.read_text())
                for e in spec["environments"]:
                    if e["id"] == env_id:
                        if value is None:
                            e.pop("carry_out", None)
                        else:
                            e["carry_out"] = value
                tmp.write_text(json.dumps(spec)); os.replace(tmp, flip)
                gate.refresh(force=True)

            def server_shows(loc):
                """Whether the server's own lock (polled on its own world-reload clock) still returns the keepsake."""
                status, body = _raw(url, "POST", f"/v1/default/banks/{bank}/memories/recall",
                                    {"query": "conformance keepsake code", "tags": [personal_labels(a, floor, src=l1).id],
                                     "tags_match": "any"}, as_(a, loc))
                return status != 200 or codes["carry"] in body

            before_hold = json.loads(flip.read_text())
            held_value = next((e.get("carry_out") for e in before_hold["environments"] if e["id"] == env_id), None)
            settle = max(2 * gate.check_every, 1.0) + 1.0
            try:
                set_hold([])
                deadline3 = time.time() + settle + 10
                while time.time() < deadline3 and (sees(a, l2, codes["carry"], "conformance keepsake code") or (probes and server_shows(l2))):
                    time.sleep(0.5)                                            # both sides re-read the world within the interval
                withheld_elsewhere = not sees(a, l2, codes["carry"], "conformance keepsake code")
                kept_at_source = sees(a, l1, codes["carry"], "conformance keepsake code")
                validator_hidden = not probes or not server_shows(l2)
                marked = any(i.withheld and i.source == l1 for i in mem.personal(a)) if caps.list_by_label_set else True
                derived = [i for i in (mem.store.list(mem.core.partition_for(personal_labels(a, floor, src=l1)), personal_labels(a, floor, src=l1).id)
                                       if caps.list_by_label_set else []) if i.kind == "derived"]
                derived_ids = {d.write_id for d in derived}
                elsewhere = mem.recall(Context(a, l2), "conformance keepsake code", k=20)
                derived_hidden = not any(codes["carry"] in r.text or r.write_id in derived_ids for r in elsewhere)
            finally:
                set_hold(held_value)                                           # back to what the host had
            deadline4 = time.time() + settle + 10
            while time.time() < deadline4 and (not sees(a, l2, codes["carry"], "conformance keepsake code") or (probes and not server_shows(l2))):
                time.sleep(0.5)
            released = sees(a, l2, codes["carry"], "conformance keepsake code") and (not probes or server_shows(l2))
            ok("held-withheld", withheld_elsewhere and kept_at_source and validator_hidden and marked and released,
               f"withheld at {l2} {withheld_elsewhere}, kept at {l1} {kept_at_source}, validator hid it {validator_hidden}, "
               f"owner's view marked it {marked}, released again {released}")
            if derived:
                ok("held-derived", derived_hidden, f"{len(derived)} derived item(s) in the held set, none recalled elsewhere: {derived_hidden}")
            else:
                skip("held-derived", "the store derived nothing from the held set within the wait")
        if not caps.list_by_label_set:
            skip("owner-view", "the store cannot list by label set")
        elif carry_type and kept_id:
            mine = mem.personal(a)
            theirs = mem.personal(b)
            own_sets = {ls_id for ls_id, _ in mem.core.personal_sets(a)}                # plain, by class, by source
            own_ok = any(i.write_id == kept_id for i in mine) and all(i.label_set in own_sets for i in mine)
            if caps.delete:
                before = sum(i.kind == "memory" for i in mine)
                try:
                    mem.forget(b, kept_id)
                    stranger = "allowed"
                except PermissionError:
                    stranger = "refused"
                gone = mem.forget(a, kept_id)
                after = [i for i in mem.personal(a) if i.kind == "memory"]
                removed = gone and all(i.write_id != kept_id for i in after) and len(after) == before - 1
                ok("owner-view", own_ok and not theirs and stranger == "refused" and removed,
                   f"{before} items listed, {b}'s forget {stranger}, {a}'s forget {'removed exactly it' if removed else 'did not remove exactly it'}, {len(after)} left")
            else:
                ok("owner-view", own_ok and not theirs, f"{len(mine)} items listed; the store cannot delete")
        else:
            skip("owner-view", "no ordinary location lets any memory type out")

        legacy_class = next((c for c in CLASSES if not w.consolidates(c)), None)
        if not (caps.list_by_label_set and caps.delete):
            skip("class-legacy", "the store cannot list by label set or delete")
        elif legacy_class is None:
            skip("class-legacy", "no class in the world is marked consolidate: false")
        elif not carry_type:
            skip("class-legacy", "no ordinary location lets any memory type out")
        else:
            # What a 0.5.x client, or a client before the class was marked, did: the class set's item in the shared
            # partition. Written straight into the store under memgate's own labels and write id.
            from memgate.store import Item
            legacy_ls = gate.registry.register(personal_labels(a, legacy_class))
            legacy_id = keep(f"w_{legacy_ls}_{uuid.uuid4().hex[:16]}")
            mem.store.ensure(bank)
            mem.store.put(Item(text=f"Kept before the flag flipped: the legacy code is {codes['legacy']}.", label_set=legacy_ls,
                               write_id=legacy_id, partition=bank), agent=a, location=l1)
            deadline2 = time.time() + wait_s
            while mem.pending_operations() and time.time() < deadline2:
                time.sleep(5)
            listed = any(i.write_id == legacy_id for i in mem.personal(a))
            recalled = sees(a, l2 or l1, codes["legacy"], "legacy code")
            gone = mem.forget(a, legacy_id)
            still = any(i.write_id == legacy_id for i in mem.personal(a))
            ok("class-legacy", listed and gone and not still,
               f"listed {listed}, recalled {recalled}, forgotten {gone}, still listed {still}")
        if ha:
            ok("ha-inside", sees(a, v, codes["ha"], "conformance dial"))
            ok("ha-outside", not sees(a, l1, codes["ha"], "conformance dial"))
            vault_bank = partition_bank(bank, v)
            if caps.partitions and hindsight:
                docs = lambda bk: json.loads(_raw(purl if bk == vault_bank else url, "GET",
                                                  f"/v1/default/banks/{bk}/documents?limit=500", None, admin)[1] or "{}").get("items", [])
                reg = gate.registry.all()
                in_v = lambda d: v in reg[d["tags"][0]].locs
                ok("ha-partition", any(in_v(d) for d in docs(vault_bank)) and not any(in_v(d) for d in docs(bank)))
                if probes:
                    status, _ = _raw(purl, "POST", f"/v1/default/banks/{vault_bank}/memories/recall", {"query": "x"}, as_(a, l1))
                    ok("ha-partition-search", status == 403, f"status {status}")
            elif not caps.partitions:
                skip("ha-partition", "the store has no partitions: a high-assurance location is kept apart by its label set only")
                skip("ha-partition-search", "the store has no partitions")
            else:
                skip("ha-partition", "conformance can only read Hindsight's partitions directly")
                skip("ha-partition-search", "conformance can only probe Hindsight's validator directly")
            mine_ls = gate.registry.register(personal_labels(a))
            validator_status = None
            if probes:
                validator_status, _ = _raw(url, "POST", f"/v1/default/banks/{bank}/memories",
                                           {"items": [{"content": "sealed", "tags": [mine_ls]}]}, as_(a, v))
            try:
                mem.carry_out(Context(a, v), "sealed", "opinion", source=personal_labels(a))
                client_refused = False
            except PermissionError:
                client_refused = True
            ok("ha-seal", client_refused and validator_status in (None, 403),
               f"client refused {client_refused}" + (f", validator {validator_status}" if validator_status is not None else ""))
            if partition_url and probes:
                s1, _ = _raw(url, "POST", f"/v1/default/banks/{vault_bank}/memories/recall", {"query": "x"}, as_(a, v))
                s2, _ = _raw(purl, "POST", f"/v1/default/banks/{bank}/memories/recall", {"query": "x"}, as_(a, l1))
                ok("split-scope", s1 == 403 and s2 == 403, f"shared server on a partition {s1}, partition server on shared {s2}")
            else:
                skip("split-scope", "not a split deployment (no --partition-url)")
        else:
            for cid in ("ha-inside", "ha-outside", "ha-partition", "ha-partition-search", "ha-seal", "split-scope"):
                skip(cid, "the world has no high-assurance location")
        # The location's view and purge (0.8.0): last, because it empties l1.
        if not (caps.list_by_label_set and caps.delete):
            skip("location-view", "the store cannot list by label set or delete")
        else:
            note_code = uuid.uuid4().hex[:8].upper()
            keep(mem.keep_note(Context(a, l1), f"{a}'s private note at {l1}: {note_code}."))
            deadline5 = time.time() + wait_s
            while mem.pending_operations() and time.time() < deadline5:
                time.sleep(2)
            listed = mem.location(l1)
            conv_listed = any((i.write_id == conv_id or codes["conv"] in i.text) and i.participants == sorted((a, b)) for i in listed)
            note_hidden = not any(note_code in i.text for i in listed)
            others_out = not any(codes[k] in i.text for i in listed for k in ("carry", "class", "ha") if k in codes)
            counts = mem.forget_location(l1)
            gone = not sees(a, l1, codes["conv"]) and not sees(b, l1, codes["conv"])
            empty = mem.location(l1) == []
            note_gone = not sees(a, l1, note_code, "private note")
            again = mem.forget_location(l1)
            ok("location-view", conv_listed and note_hidden and others_out and counts["writes"] >= 1 and counts["notes"] >= 1
               and gone and empty and note_gone and again["writes"] == 0 and again["notes"] == 0,
               f"listed {len(listed)} item(s) with the conversation {conv_listed}, note hidden {note_hidden}, nothing of other sets {others_out}; "
               f"forgot {counts['writes']} write(s), {counts['derived']} derived, {counts['notes']} note(s); recalled after {not gone}, "
               f"listed after {not empty}, note recalled after {not note_gone}; repeat {again['writes']}/{again['notes']}")
    finally:
        if hindsight:
            for bk in mem.partitions():
                try:
                    mem._call("DELETE", f"/v1/default/banks/{bk}", None, role="admin")
                except (HindsightError, OSError):
                    pass
        elif caps.delete:
            for wid in created:                               # exactly this run's writes, nothing else
                try:
                    for part in mem.core.partitions_of_write(wid):
                        mem.store.delete(part, wid)
                except Exception:                             # cleanup is best effort
                    pass
    return list(checks.values())


def report(checks: list[Check]) -> str:
    mark = {"pass": "PASS", "fail": "FAIL", "skip": "skip"}
    lines = [f"{mark[c.status]:4}  {c.id:20} {c.claim}" + (f"  [{c.detail}]" if c.detail else "") for c in checks]
    n = {s: sum(c.status == s for c in checks) for s in ("pass", "fail", "skip")}
    lines.append(f"\n{n['pass']} passed, {n['fail']} failed, {n['skip']} skipped")
    return "\n".join(lines)
