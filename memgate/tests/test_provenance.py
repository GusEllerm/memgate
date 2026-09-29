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
        for table in ("recalls", "writes", "audit"):
            assert shared.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
    ha = sqlite3.connect(tmp_path / "provenance-ha-vault.sqlite")
    assert ha.execute("SELECT COUNT(*) FROM recalls").fetchone()[0] == 1


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
