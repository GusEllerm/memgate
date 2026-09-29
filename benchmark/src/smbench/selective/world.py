"""Seeded worlds for the selective-memory benchmark.

A world is agents, locations and a schedule of conversations. Each conversation carries planted facts:
a topic with a unique code (the canary), stated verbatim in the dialogue. Scenarios:

- S1 witness: pairs and trios talk; only those present, in that location, should recall it.
- S2 triad: {A,B}, {A,C}, then {A,B,C} in one location, each with its own fact.
- S3 retelling: A and B share two facts; later A retells one of them with a newcomer X present.
  X should recall the retold fact and never the untold one.

The dialogue itself is written by an LLM (see `dialogue.py`); this module only plans the world.
"""

from __future__ import annotations

import random
from dataclasses import asdict, dataclass, field

AGENTS = ["ada", "bo", "cy", "dee", "eli", "fay"]
LOCATIONS = ["lab", "cafe", "garden"]
TOPICS = [
    "the code for the greenhouse door", "the name chosen for the new research project", "the password for the old archive",
    "the combination of the lab safe", "the name of the rescued cat", "the room booked for the secret party",
    "the nickname for the new telescope", "the key phrase for the bike lock", "the label on the sealed crate",
    "the codename for the field trip", "the name of the prototype robot", "the recipe codeword for the cake contest",
    "the call sign for the radio test", "the locker number for the spare keys", "the title chosen for the joint paper",
    "the name picked for the garden pond", "the code for the storeroom", "the password for the shared drive",
]
WORDS = ["QUILL", "EMBER", "CEDAR", "ORBIT", "MAPLE", "FROST", "LUMEN", "HARBOR", "PIXEL", "TUNDRA", "SAFFRON",
         "COBALT", "WILLOW", "ZEPHYR", "GARNET", "MOSAIC", "NECTAR", "RIDGE"]


@dataclass
class Fact:
    id: str
    topic: str
    code: str

    @property
    def sentence(self) -> str:
        return f"{self.topic[0].upper()}{self.topic[1:]} is {self.code}."


@dataclass
class Conversation:
    id: str
    scenario: str
    location: str
    participants: list[str]
    facts: list[str]                                   # fact ids stated in this conversation
    retells: dict[str, str] = field(default_factory=dict)   # fact id -> id of the conversation it came from
    speaker_for: dict[str, str] = field(default_factory=dict)  # fact id -> who states it
    turns: list[dict] = field(default_factory=list)    # filled by dialogue.py: [{"speaker", "text"}]


@dataclass
class World:
    seed: int
    agents: list[str]
    locations: list[str]
    facts: dict[str, Fact]
    conversations: list[Conversation]

    def to_json(self) -> dict:
        return {"seed": self.seed, "agents": self.agents, "locations": self.locations,
                "facts": {k: asdict(v) for k, v in self.facts.items()},
                "conversations": [asdict(c) for c in self.conversations]}

    @classmethod
    def from_json(cls, d: dict) -> "World":
        return cls(d["seed"], d["agents"], d["locations"], {k: Fact(**v) for k, v in d["facts"].items()},
                   [Conversation(**c) for c in d["conversations"]])

    def memgate_world(self) -> dict:
        """The world as memgate's world.json: one open environment, no high-assurance locations (S1–S3)."""
        return {"environments": [{"id": f"w{self.seed}"}],
                "locations": [{"id": l, "environment": f"w{self.seed}"} for l in self.locations],
                "agents": self.agents}


def plan(seed: int) -> World:
    rng = random.Random(seed)
    agents = [f"{a}{seed}" for a in AGENTS]                   # names unique per world
    locations = [f"{l}{seed}" for l in LOCATIONS]
    topics, words = rng.sample(TOPICS, len(TOPICS)), rng.sample(WORDS, len(WORDS))
    facts: dict[str, Fact] = {}
    convs: list[Conversation] = []

    def fact() -> str:
        i = len(facts)
        f = Fact(f"f{seed}-{i}", topics[i], f"{words[i]}-{rng.randint(1000, 9999)}")
        facts[f.id] = f
        return f.id

    def conv(scenario, loc, people, n_facts=1, **kw) -> Conversation:
        c = Conversation(f"c{seed}-{len(convs)}", scenario, loc, sorted(people), [fact() for _ in range(n_facts)], **kw)
        c.speaker_for = {f: rng.choice(c.participants) for f in c.facts}
        convs.append(c)
        return c

    # S1: four witness conversations, pairs and trios in random locations.
    for _ in range(4):
        conv("S1", rng.choice(locations), rng.sample(agents, rng.choice([2, 2, 3])))
    # S2: the triad, all in one location.
    a, b, c = rng.sample(agents, 3)
    loc = rng.choice(locations)
    conv("S2", loc, [a, b])
    conv("S2", loc, [a, c])
    conv("S2", loc, [a, b, c])
    # S3: A and B share two facts; later A retells the first with newcomer X present.
    a, b, x = rng.sample(agents, 3)
    loc = rng.choice(locations)
    src = conv("S3", loc, [a, b], n_facts=2)
    told = src.facts[0]
    retold = Conversation(f"c{seed}-{len(convs)}", "S3", loc, sorted([a, b, x]), [told],
                          retells={told: src.id}, speaker_for={told: a})
    convs.append(retold)
    return World(seed, agents, locations, facts, convs)
