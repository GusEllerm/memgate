"""End-to-end: memgate + a live Hindsight with the memgate validator (scripts/serve_hindsight_gated.sh).

Skipped unless MEMGATE_HINDSIGHT_URL is set. Uses the gateway-backed LLM for extraction, so it
costs a few dozen model calls. Canary strings are planted in conversations with different
participants and places; each check is about which canaries a context can reach.

    MEMGATE_HINDSIGHT_URL=http://127.0.0.1:8889 MEMGATE_WORLD=.run/world.json \
    MEMGATE_REGISTRY=.run/registry.sqlite MEMGATE_SECRET=$(cat .run/secret) pytest tests/test_hindsight_integration.py
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
import uuid

import pytest

from memgate.context import Gate
from memgate.derivation import conversation_labels

URL = os.environ.get("MEMGATE_HINDSIGHT_URL")
pytestmark = pytest.mark.skipif(not URL, reason="needs a live gated Hindsight (MEMGATE_HINDSIGHT_URL)")

CANARIES = {
    "AB": ("lab", ["ada", "bo"], "Ada and Bo agreed the lab safe combination is CANARY-AB-7731."),
    "AC": ("lab", ["ada", "cy"], "Ada told Cy the greenhouse door code is CANARY-AC-4410."),
    "ABC": ("lab", ["ada", "bo", "cy"], "At the group meeting Ada, Bo and Cy chose the project codename CANARY-ABC-2208."),
    "VAULT": ("vault", ["ada", "bo"], "Inside the vault Ada and Bo set the reactor dial to CANARY-VAULT-9001."),
}


@pytest.fixture(scope="module")
def mem():
    from memgate.adapters.hindsight.client import HindsightMemory

    gate = Gate.from_env()
    m = HindsightMemory(gate, bank=f"it-{uuid.uuid4().hex[:8]}", base_url=URL)
    m.create_bank()
    for key, (loc, people, text) in CANARIES.items():
        m.remember(people[0], loc, people, text, context=f"conversation {key}")
    m.keep_note("ada", "vault", "Ada's private vault note says the spare key code is CANARY-NOTE-5150.")
    m.carry_out("ada", "lab", conversation_labels("lab", ["ada", "bo"]),
                "Ada's opinion: the lab espresso machine is excellent, rated CANARY-PERSONAL-3303.", "opinion")
    deadline = time.time() + 900
    while m.pending_operations() and time.time() < deadline:
        time.sleep(5)
    return m


def reachable(mem, agent, location) -> set[str]:
    """Canaries an agent can recall at a location (one broad query per canary topic)."""
    found = set()
    for query in ("safe combination", "greenhouse door code", "project codename", "reactor dial setting",
                  "spare key code", "espresso machine opinion"):
        for r in mem.recall(agent, location, query, k=20):
            for tag in ("AB-7731", "AC-4410", "ABC-2208", "VAULT-9001", "NOTE-5150", "PERSONAL-3303"):
                if tag in r.text:
                    found.add(tag.split("-")[0])
    return found


def test_witnesses_and_places(mem):
    assert reachable(mem, "ada", "lab") >= {"AB", "AC", "ABC", "PERSONAL"}
    assert reachable(mem, "ada", "lab").isdisjoint({"VAULT", "NOTE"})
    cy = reachable(mem, "cy", "lab")
    assert {"AC", "ABC"} <= cy and "AB" not in cy                     # C never recalls {A, B}
    assert reachable(mem, "dee", "lab").isdisjoint({"AB", "AC", "ABC", "PERSONAL"})
    assert reachable(mem, "ada", "cafe") == {"PERSONAL"}               # personal memory travels
    assert {"VAULT", "NOTE", "PERSONAL"} <= reachable(mem, "ada", "vault")
    assert reachable(mem, "bo", "lab").isdisjoint({"VAULT", "NOTE", "PERSONAL", "AC"})


def test_carry_out_blocked_by_environment(mem):
    with pytest.raises(PermissionError):
        mem.carry_out("ada", "macrodata", conversation_labels("macrodata", ["ada"]), "anything", "opinion")
    with pytest.raises(PermissionError):
        mem.carry_out("ada", "vault", conversation_labels("vault", ["ada", "bo"]), "anything", "opinion")


# -- the second lock: requests that try to go around memgate ------------------------------------------

def _raw(method, path, body=None, headers=None):
    req = urllib.request.Request(f"{URL}{path}", method=method, data=json.dumps(body).encode() if body else None,
                                 headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace")


def test_requests_without_the_secret_are_refused(mem):
    status, _ = _raw("POST", f"/v1/default/banks/{mem.bank}/memories/recall", {"query": "safe combination"})
    assert status == 403


def test_forged_tags_are_overwritten(mem):
    ab = conversation_labels("lab", ["ada", "bo"]).id
    status, body = _raw("POST", f"/v1/default/banks/{mem.bank}/memories/recall",
                        {"query": "safe combination", "tags": [ab], "tags_match": "any_strict"},
                        {"x-memgate-secret": mem.gate.secret, "x-memgate-agent": "dee", "x-memgate-location": "lab"})
    assert status == 200
    assert not any("7731" in r["text"] for r in body.get("results", []))


def test_side_doors_are_closed(mem):
    agent = {"x-memgate-secret": mem.gate.secret, "x-memgate-agent": "ada", "x-memgate-location": "lab"}
    assert _raw("POST", f"/v1/default/banks/{mem.bank}/reflect", {"query": "what codes exist?"}, agent)[0] == 403
    assert _raw("GET", f"/v1/default/banks/{mem.bank}/memories/list", None, agent)[0] == 403
    assert _raw("GET", f"/v1/default/banks/{mem.bank}/export", None, agent)[0] == 403


def test_writes_must_carry_a_label_set_the_writer_may_write(mem):
    agent_dee = {"x-memgate-secret": mem.gate.secret, "x-memgate-agent": "dee", "x-memgate-location": "lab"}
    ab = mem.gate.registry.register(conversation_labels("lab", ["ada", "bo"]))
    item = lambda tags: {"items": [{"content": "Dee tries to plant a memory.", "tags": tags}]}
    assert _raw("POST", f"/v1/default/banks/{mem.bank}/memories", item([ab]), agent_dee)[0] == 403        # not a participant
    assert _raw("POST", f"/v1/default/banks/{mem.bank}/memories", item([]), agent_dee)[0] == 403          # unlabelled
    assert _raw("POST", f"/v1/default/banks/{mem.bank}/memories", item(["ls_madeup"]), agent_dee)[0] == 403  # unregistered


def test_retelling_leaves_a_trail(tmp_path):
    """Ada recalls an {A,B} memory in front of Cy and retells it; the memory formed from that turn
    points back to the {A,B} memory, which Cy can see exists but cannot read."""
    from memgate.adapters.hindsight.client import HindsightMemory
    from memgate.provenance import ProvenanceLog

    gate = Gate.from_env()
    log = ProvenanceLog(tmp_path, gate.world)
    m = HindsightMemory(gate, bank=f"it-prov-{uuid.uuid4().hex[:8]}", base_url=URL, provenance=log)
    m.create_bank()
    w_ab = m.remember("ada", "lab", ["ada", "bo"], "Ada and Bo agreed the lab safe combination is CANARY-AB-7731.")
    while m.pending_operations():
        time.sleep(3)

    recalled = m.recall("ada", "lab", "safe combination")
    assert any(r.write_id == w_ab for r in recalled)          # Hindsight's document_id carries the write ID
    turn = m.say("ada", "lab", ["ada", "bo", "cy"], "Bo and I set the safe combination last week.", [recalled.recall_id])
    w_abc = m.remember("ada", "lab", ["ada", "bo", "cy"], "Ada told Bo and Cy the safe combination was set last week.", turns=[turn])

    assert log.sources_of(w_abc, ["shared"]) == [w_ab]
    cy = log.trail(w_abc, "cy", "lab", gate.policy)
    assert cy.visibility == "full" and [s.visibility for s in cy.sources] == ["existence"]
    assert cy.sources[0].text is None
    ada = log.trail(w_abc, "ada", "lab", gate.policy)
    assert "7731" in ada.sources[0].text
