import pytest

from memgate.policy import Policy
from memgate.registry import Registry
from memgate.world import World


@pytest.fixture
def world() -> World:
    w = World()
    w.add_environment("campus")                                   # open: every memory type may be carried out
    w.add_environment("studio", carry_out={"opinion", "skill"})   # selective
    w.add_environment("severed-floor", carry_out=())              # Severance
    w.add_location("lab", "campus")
    w.add_location("cafe", "campus")
    w.add_location("gallery", "studio")
    w.add_location("macrodata", "severed-floor")
    w.add_location("vault", "campus", high_assurance=True)
    w.add_agents("ada", "bo", "cy", "dee")
    return w


@pytest.fixture
def registry() -> Registry:
    return Registry()


@pytest.fixture
def policy(world, registry) -> Policy:
    return Policy(world, registry)
