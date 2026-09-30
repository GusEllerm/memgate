"""Recall, write and carry-out decisions, checked against the rules in the Decision Log."""

from memgate.derivation import conversation_labels, personal_labels, personal_note_labels


def reg(registry, ls):
    registry.register(ls)
    return ls.id


def test_policies_validate_against_schema(policy):
    assert policy.validate() == []


def test_only_witnesses_recall_a_conversation_in_its_location(policy, registry):
    trio = reg(registry, conversation_labels("lab", ["ada", "bo", "cy"]))
    assert trio in policy.allowed_ids("ada", "lab")        # a witness, in the location, alone
    assert trio not in policy.allowed_ids("dee", "lab")    # not a witness
    assert trio not in policy.allowed_ids("ada", "cafe")   # a witness, elsewhere


def test_personal_memory_readable_by_owner_everywhere_and_no_one_else(policy, registry):
    mine = reg(registry, personal_labels("ada"))
    for loc in ("lab", "cafe", "vault", "macrodata"):
        assert mine in policy.allowed_ids("ada", loc)
    assert mine not in policy.allowed_ids("bo", "lab")


def test_high_assurance_is_outbound_only(policy, registry):
    inside = reg(registry, conversation_labels("vault", ["ada", "bo"]))
    note = reg(registry, personal_note_labels("ada", "vault"))
    mine = reg(registry, personal_labels("ada"))
    assert {inside, note, mine} <= policy.allowed_ids("ada", "vault")   # personal memory may come in
    assert inside not in policy.allowed_ids("ada", "lab")
    assert note not in policy.allowed_ids("ada", "lab")


def test_gus_scenario_ab_ac_then_abc(policy, registry):
    ab = reg(registry, conversation_labels("lab", ["ada", "bo"]))
    ac = reg(registry, conversation_labels("lab", ["ada", "cy"]))
    abc = reg(registry, conversation_labels("lab", ["ada", "bo", "cy"]))
    assert {ab, ac, abc} <= policy.allowed_ids("ada", "lab")
    assert ab not in policy.allowed_ids("cy", "lab")      # C never recalls {A, B}
    assert {ac, abc} <= policy.allowed_ids("cy", "lab")   # but keeps what was said with C present


def test_carry_out_follows_the_environment(policy):
    lab = conversation_labels("lab", ["ada", "bo"])
    gallery = conversation_labels("gallery", ["ada", "bo"])
    macro = conversation_labels("macrodata", ["ada", "bo"])
    assert policy.may_carry_out("ada", "lab", lab, "fact")                # open
    assert policy.may_carry_out("ada", "gallery", gallery, "opinion")     # selective: opinions out
    assert not policy.may_carry_out("ada", "gallery", gallery, "fact")    # selective: facts stay
    assert not policy.may_carry_out("ada", "macrodata", macro, "opinion")  # Severance: nothing leaves


def test_nothing_is_carried_out_of_high_assurance(policy):
    assert not policy.may_carry_out("ada", "vault", conversation_labels("vault", ["ada"]), "opinion")


def test_only_a_witness_can_carry_a_memory_out(policy):
    assert not policy.may_carry_out("dee", "lab", conversation_labels("lab", ["ada", "bo"]), "fact")


def test_carry_out_only_where_the_source_is_readable(policy):
    lab = conversation_labels("lab", ["ada", "bo"])
    assert policy.may_carry_out("ada", "lab", lab, "fact")
    assert not policy.may_carry_out("ada", "cafe", lab, "fact")        # same environment, other location
    assert not policy.may_carry_out("ada", "macrodata", lab, "fact")   # claimed source, wrong place


def test_writes_follow_the_labels(policy):
    assert policy.may_write("ada", "lab", conversation_labels("lab", ["ada", "bo"]))      # a participant, there
    assert not policy.may_write("dee", "lab", conversation_labels("lab", ["ada", "bo"]))  # not a participant
    assert not policy.may_write("ada", "cafe", conversation_labels("lab", ["ada", "bo"]))  # not there
    assert policy.may_write("ada", "cafe", personal_labels("ada"))                        # own personal memory
    assert not policy.may_write("bo", "cafe", personal_labels("ada"))                     # never another's identity
    assert policy.may_write("ada", "lab", personal_note_labels("ada", "lab"))
    assert not policy.may_write("ada", "cafe", personal_note_labels("ada", "lab"))


def test_high_assurance_write_seal(policy):
    # Inside a high-assurance location every write must carry that location's label.
    assert policy.may_write("ada", "vault", conversation_labels("vault", ["ada", "bo"]))
    assert policy.may_write("ada", "vault", personal_note_labels("ada", "vault"))
    assert not policy.may_write("ada", "vault", personal_labels("ada"))        # personal memory: no way out
    assert policy.may_write("ada", "lab", personal_labels("ada"))              # outside, as before


TOO_BROAD = '''
@id("too-broad-grant")
permit (principal == Agent::"ada", action == Action::"read", resource);
'''


def test_seal_holds_against_an_over_broad_grant(world, registry):
    """The read rule alone already keeps high-assurance memories in place; the seal is the backstop
    for a later rule that grants too much (e.g. a location hierarchy granting a parent's labels)."""
    from memgate.policy import POLICIES, Policy

    vault = reg(registry, conversation_labels("vault", ["ada"]))
    with_seal = Policy(world, registry, policies=POLICIES + TOO_BROAD)
    assert vault not in with_seal.allowed_ids("ada", "lab")
    without_seal = POLICIES[: POLICIES.index("// High assurance")] + POLICIES[POLICIES.index("// Carrying"):]
    assert vault in Policy(world, registry, policies=without_seal + TOO_BROAD).allowed_ids("ada", "lab")
