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


def test_empty_worlds_are_refused():
    assert check_world({}) and check_world([]) and check_world({"environments": [], "locations": [], "agents": []})
