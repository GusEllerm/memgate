"""World files are checked before memgate uses them (memgate check-world, and memgate serve)."""

from memgate.worldcheck import check_world

GOOD = {"environments": [{"id": "campus"}, {"id": "studio", "carry_out": ["opinion", "skill"]}],
        "locations": [{"id": "lab", "environment": "campus"},
                      {"id": "vault", "environment": "campus", "high_assurance": True},
                      {"id": "gallery", "environment": "studio"}],
        "agents": ["ada", "bo"]}


def test_a_good_world_passes():
    assert check_world(GOOD) == []


def test_each_mistake_is_reported():
    bad = {"environments": [{"id": "e", "carry_out": ["fact", "gossip"]}, {"id": "e"}],
           "locations": [{"id": "x--ha--y", "environment": "nope", "high_assurance": "yes"}],
           "agents": ["a", "a"], "extra": 1}
    errors = "\n".join(check_world(bad))
    for expected in ("gossip", "--ha--", "'nope' is not listed", "high_assurance must be", "duplicate agents",
                     "duplicate environments", "unknown top-level keys"):
        assert expected in errors, expected


def test_malformed_worlds_are_refused_but_an_empty_one_is_valid():
    """0.8.2: a well-formed world that lists nothing yet is valid (a fresh deployment starts on it), with warnings;
    a world that is not an object, or lacks one of the three lists, is still refused."""
    from memgate.worldcheck import world_warnings
    assert check_world({}) and check_world([]) and check_world({"locations": [], "agents": []})
    empty = {"environments": [], "locations": [], "agents": []}
    assert check_world(empty) == [] and len(world_warnings(empty)) == 2
    assert world_warnings({"environments": [{"id": "e"}], "locations": [{"id": "l", "environment": "e"}], "agents": ["a"]}) == []
