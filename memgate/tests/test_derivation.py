import pytest

from memgate.derivation import CrossLabelSetMerge, check_merge, conversation_labels, derived_labels, personal_labels
from memgate.labels import NOBODY


def test_participants_intersect_locations_combine():
    d = derived_labels([conversation_labels("lab", ["ada", "bo"]), conversation_labels("lab", ["ada", "cy"])])
    assert d.withs == {"ada"} and d.locs == {"lab"}


def test_no_shared_participant_means_nobody(policy, registry):
    d = derived_labels([conversation_labels("lab", ["ada", "bo"]), conversation_labels("lab", ["cy"])])
    assert d.withs == {NOBODY}
    registry.register(d)
    for agent in ("ada", "bo", "cy", "dee"):
        assert d.id not in policy.allowed_ids(agent, "lab")


def test_summary_of_ab_and_abc_stays_hidden_from_c(policy, registry):
    d = derived_labels([conversation_labels("lab", ["ada", "bo"]), conversation_labels("lab", ["ada", "bo", "cy"])])
    registry.register(d)
    assert d.id in policy.allowed_ids("bo", "lab")
    assert d.id not in policy.allowed_ids("cy", "lab")


def test_crossing_locations_is_unreadable_from_either(policy, registry):
    d = derived_labels([conversation_labels("lab", ["ada"]), conversation_labels("cafe", ["ada"])])
    registry.register(d)
    assert d.id not in policy.allowed_ids("ada", "lab") and d.id not in policy.allowed_ids("ada", "cafe")


def test_personal_source_keeps_owner(policy, registry):
    d = derived_labels([personal_labels("ada"), conversation_labels("lab", ["ada", "bo"])])
    assert d.selfs == {"ada"} and d.withs == {"ada", "bo"}


def test_merge_only_within_a_label_set():
    a = conversation_labels("lab", ["ada", "bo"]).id
    b = conversation_labels("lab", ["ada", "bo", "cy"]).id
    assert check_merge([a, a]) == a
    with pytest.raises(CrossLabelSetMerge):
        check_merge([a, b])
