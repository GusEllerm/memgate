from memgate.derivation import conversation_labels


def test_register_is_idempotent_and_round_trips(registry):
    ls = conversation_labels("lab", ["ada", "bo"])
    assert registry.register(ls) == registry.register(ls) == ls.id
    assert len(registry) == 1
    assert registry.get(ls.id) == ls
