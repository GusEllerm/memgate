"""Provenance across agents, shown to each asker under the recall rules, and partitioned for high assurance."""

import sqlite3

import pytest

from memgate.derivation import conversation_labels, personal_labels
from memgate.provenance import ProvenanceLog


@pytest.fixture
def log(tmp_path, world):
    return ProvenanceLog(tmp_path, world)


def write(log, registry, wid, author, location, labels, text, **kw):
    registry.register(labels)
    log.record_write(wid, author, location, labels.id, kw.pop("kind", "conversation"), text, **kw)
    return labels.id


def test_retelling_is_traceable_and_shown_per_asker(log, registry, policy):
    ab = write(log, registry, "w_ab", "ada", "lab", conversation_labels("lab", ["ada", "bo"]),
               "Ada and Bo agreed the safe code is 7731.")
    # Later, with Cy present: Ada recalls the {A,B} memory, then speaks.
    rid = log.record_recall("ada", "lab", "safe code", {ab}, [("w_ab", ab)])
    tid = log.record_turn("ada", "lab", ["ada", "bo", "cy"], "Bo and I set the safe code last week.", [rid])
    write(log, registry, "w_abc", "ada", "lab", conversation_labels("lab", ["ada", "bo", "cy"]),
          "Ada told Bo and Cy the safe code was set last week.", turns=[tid])

    assert log.sources_of("w_abc", ["shared"]) == ["w_ab"]

    ada = log.trail("w_abc", "ada", "lab", policy)
    assert ada.visibility == "full" and ada.sources[0].visibility == "full"
    assert "7731" in ada.sources[0].text

    cy = log.trail("w_abc", "cy", "lab", policy)
    assert cy.visibility == "full"
    src = cy.sources[0]
    assert src.visibility == "existence" and src.text is None and src.location == "lab"   # Cy learns a source exists, not what it says

    dee = log.trail("w_abc", "dee", "lab", policy)
    assert dee.visibility == "existence" and dee.sources == []   # nothing of what an unreadable memory was built from


def test_high_assurance_recalls_and_writes_stay_in_their_partition(log, registry, policy, tmp_path):
    vault = write(log, registry, "w_vault", "ada", "vault", conversation_labels("vault", ["ada", "bo"]),
                  "Reactor dial set to 9001.")
    log.record_recall("ada", "vault", "reactor dial", {vault}, [("w_vault", vault)])
    log.audit("vault", "recall", agent="ada")

    shared_path = tmp_path / "provenance-shared.sqlite"
    if shared_path.exists():                     # created only if something was written outside the vault
        shared = sqlite3.connect(shared_path)
        for table in ("activity", "entity", "used", "audit"):
            assert shared.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
    ha = sqlite3.connect(tmp_path / "provenance-ha-vault.sqlite")
    assert ha.execute("SELECT COUNT(*) FROM activity WHERE kind = 'recall'").fetchone()[0] == 1


def test_high_assurance_sources_are_sealed_outside(log, registry, policy):
    vault = write(log, registry, "w_vault", "ada", "vault", conversation_labels("vault", ["ada"]), "Reactor dial 9001.")
    # Ada, inside the vault, forms a personal opinion drawing on it (as if the environment allowed it).
    mine = write(log, registry, "w_mine", "ada", "vault", personal_labels("ada"),
                 "Ada thinks the reactor runs hot.", kind="carry_out", derived_from=["w_vault"])
    inside = log.trail("w_mine", "ada", "vault", policy)
    assert inside.sources and inside.sources[0].write_id == "w_vault"
    # w_mine was recorded in the vault's partition, so outside the vault even its own trail is sealed.
    assert log.trail("w_mine", "ada", "lab", policy) is None


def test_derived_from_links_directly(log, registry, policy):
    a = write(log, registry, "w_a", "ada", "lab", conversation_labels("lab", ["ada", "bo"]), "fact one")
    b = write(log, registry, "w_b", "ada", "lab", conversation_labels("lab", ["ada", "bo"]), "fact two")
    write(log, registry, "w_obs", "ada", "lab", conversation_labels("lab", ["ada", "bo"]), "an observation",
          kind="observation", derived_from=["w_a", "w_b"])
    t = log.trail("w_obs", "bo", "lab", policy)
    assert {s.write_id for s in t.sources} == {"w_a", "w_b"}


def _retelling(log, registry):
    ab = write(log, registry, "w_ab", "ada", "lab", conversation_labels("lab", ["ada", "bo"]), "safe code 7731")
    rid = log.record_recall("ada", "lab", "safe code", {ab}, [("w_ab", ab)])
    tid = log.record_turn("ada", "lab", ["ada", "bo", "cy"], "Bo and I set the safe code.", [rid])
    abc = write(log, registry, "w_abc", "ada", "lab", conversation_labels("lab", ["ada", "bo", "cy"]), "retold", turns=[tid])
    rid2 = log.record_recall("cy", "lab", "safe code", {abc}, [("w_abc", abc)])
    mine = write(log, registry, "w_cy", "cy", "lab", personal_labels("cy"), "Cy's take on it", kind="carry_out",
                 derived_from=["w_abc"])
    return ab, abc, mine


def test_impact_finds_everything_built_downstream(log, registry):
    _retelling(log, registry)
    assert log.descendants("w_ab") == [("w_abc", 1), ("w_cy", 2)]


def test_exposure_counts_what_each_agent_was_shown(log, registry):
    ab, abc, _ = _retelling(log, registry)
    assert log.exposure("ada") == {ab: 1}
    assert log.exposure("cy") == {abc: 1}
    assert log.exposure("dee") == {}


def test_flows_show_where_a_label_set_went(log, registry):
    ab, abc, mine = _retelling(log, registry)
    f = log.flows(ab)
    assert f["recalled_by"] == [("ada", "lab", 1)]
    assert [(r[0], r[1], r[4]) for r in f["derived_elsewhere"]] == [("w_abc", abc, 1), ("w_cy", mine, 2)]


def test_trail_inside_high_assurance_spans_personal_memory_from_outside(log, registry, policy):
    mine = write(log, registry, "w_mine", "ada", "cafe", personal_labels("ada"), "Ada's view of the reactor")
    rid = log.record_recall("ada", "vault", "reactor", {mine}, [("w_mine", mine)])
    tid = log.record_turn("ada", "vault", ["ada", "bo"], "I've always thought it runs hot.", [rid])
    write(log, registry, "w_vault", "ada", "vault", conversation_labels("vault", ["ada", "bo"]), "reactor runs hot", turns=[tid])
    inside = log.trail("w_vault", "ada", "vault", policy)
    assert [s.write_id for s in inside.sources] == ["w_mine"]      # the vault's log links to shared memory
    assert log.descendants("w_mine") == []                          # but the shared log never learns what the vault built


def test_prov_json_export(log, registry):
    _retelling(log, registry)
    doc = log.export_prov()
    assert "mg:w_ab" in doc["entity"] and "prov:value" not in doc["entity"]["mg:w_ab"]
    assert {r["prov:entity"] for r in doc["used"].values()} == {"mg:w_ab", "mg:w_abc"}
    assert any(r == {"prov:informed": r["prov:informed"], "prov:informant": r["prov:informant"]} for r in doc["wasInformedBy"].values())
    assert {"prov:generatedEntity": "mg:w_cy", "prov:usedEntity": "mg:w_abc"} in doc["wasDerivedFrom"].values()
    assert "mg:agent-cy" in doc["agent"]
    assert "prov:value" in log.export_prov(include_text=True)["entity"]["mg:w_ab"]


def test_a_write_recorded_again_replaces_itself(log, registry):
    ab = conversation_labels("lab", ["ada", "bo"])
    write(log, registry, "w_old", "ada", "lab", ab, "source one")
    write(log, registry, "w_new", "ada", "lab", ab, "source two")
    write(log, registry, "w_seg", "ada", "lab", ab, "draft", kind="conversation", derived_from=["w_old"])
    write(log, registry, "w_seg", "bo", "lab", ab, "final", kind="conversation", derived_from=["w_new"])
    with sqlite3.connect(log._path("shared")) as db:
        assert db.execute("SELECT author, text FROM entity WHERE id = 'w_seg'").fetchall() == [("bo", "final")]
    assert log.sources_of("w_seg", ["shared"]) == ["w_new"]              # the old sources are gone
    assert log.descendants("w_old") == []
    assert log.descendants("w_new") == [("w_seg", 1)]


def test_write_ids_carry_their_label_set():
    from memgate.provenance import write_id_for, write_id_label_set
    ls = conversation_labels("lab", ["ada", "bo"]).id
    assert write_id_for(ls, "k") == write_id_for(ls, "k") != write_id_for(ls, "j")
    assert write_id_for(ls) != write_id_for(ls)
    assert write_id_label_set(write_id_for(ls, "k")) == ls == write_id_label_set(write_id_for(ls))
    assert write_id_label_set("w_0123456789abcdef") is None                # the pre-0.4.1 form
    assert write_id_label_set("ls_x") is None and write_id_label_set("w_ls__") is None
