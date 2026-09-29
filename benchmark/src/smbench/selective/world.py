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

AGENTS = ["ada", "bo", "cy", "dee", "eli", "fay", "gus", "hana", "ivo", "jun", "kai", "lea"]
LOCATIONS = ["lab", "cafe", "garden", "library", "workshop"]

# Larger worlds build topics from shared patterns, so many facts look alike and recall must pick the
# right one out of similar distractors.
PATTERNS = ["the code for the {}", "the password for the {}", "the name chosen for the {}", "the booking reference for the {}",
            "the label on the {}", "the combination for the {}"]
OBJECTS = ["greenhouse door", "storeroom", "archive cabinet", "lab safe", "bike shed", "telescope dome", "server rack",
           "field kit", "tool chest", "seminar room", "rooftop garden", "freezer", "loading dock", "print room",
           "boat house", "sample fridge", "west stairwell", "reading room", "kiln", "darkroom"]
SIZES = {
    # S4/S5 worlds are planned by plan_env below.
    # agents, locations, S1 witness conversations, S2 triads, S3 retellings
    "small": (6, 3, 4, 1, 1),
    "large": (12, 5, 36, 3, 3),
}
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
    kind: str = "fact"          # "fact" or "opinion": environments may let one out and not the other

    @property
    def sentence(self) -> str:
        if self.kind == "opinion":
            return f"In my view, {self.topic} should be {self.code}."
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
    carry_outs: list[dict] = field(default_factory=list)  # S4/S5: [{"agent", "fact"}] carry-out attempts afterwards


@dataclass
class World:
    seed: int
    agents: list[str]
    locations: list[str]
    facts: dict[str, Fact]
    conversations: list[Conversation]
    # S4/S5 worlds: environment id -> memory types it lets out; location -> environment; high-assurance
    # locations; personal notes kept inside a location [{"agent", "location", "fact"}].
    environments: dict[str, list[str]] = field(default_factory=dict)
    location_env: dict[str, str] = field(default_factory=dict)
    high_assurance: list[str] = field(default_factory=list)
    notes: list[dict] = field(default_factory=list)

    def to_json(self) -> dict:
        return {"seed": self.seed, "agents": self.agents, "locations": self.locations,
                "facts": {k: asdict(v) for k, v in self.facts.items()},
                "conversations": [asdict(c) for c in self.conversations],
                "environments": self.environments, "location_env": self.location_env,
                "high_assurance": self.high_assurance, "notes": self.notes}

    @classmethod
    def from_json(cls, d: dict) -> "World":
        return cls(d["seed"], d["agents"], d["locations"], {k: Fact(**v) for k, v in d["facts"].items()},
                   [Conversation(**c) for c in d["conversations"]], d.get("environments", {}),
                   d.get("location_env", {}), d.get("high_assurance", []), d.get("notes", []))

    def env_of(self, location: str) -> str:
        return self.location_env.get(location, f"w{self.seed}")

    def memgate_world(self) -> dict:
        """The world as memgate's world.json. S1–S3 worlds have one open environment."""
        envs = self.environments or {f"w{self.seed}": ["fact", "opinion", "skill", "episode"]}
        return {"environments": [{"id": e, "carry_out": types} for e, types in envs.items()],
                "locations": [{"id": l, "environment": self.env_of(l), "high_assurance": l in self.high_assurance}
                              for l in self.locations],
                "agents": self.agents}


def plan(seed: int, size: str = "small") -> World:
    if size == "env":
        return plan_env(seed)
    n_agents, n_locs, n_s1, n_s2, n_s3 = SIZES[size]
    rng = random.Random(seed)
    agents = [f"{a}{seed}" for a in AGENTS[:n_agents]]        # names unique per world
    locations = [f"{l}{seed}" for l in LOCATIONS[:n_locs]]
    if size == "small":
        topics, words = rng.sample(TOPICS, len(TOPICS)), rng.sample(WORDS, len(WORDS))
    else:
        topics = rng.sample([p.format(o) for p in PATTERNS for o in OBJECTS], len(PATTERNS) * len(OBJECTS))
        words = [f"{w}{i}" if i else w for i in range(4) for w in WORDS]     # enough distinct words
        rng.shuffle(words)
    used_codes: set[str] = set()
    facts: dict[str, Fact] = {}
    convs: list[Conversation] = []

    def fact() -> str:
        i = len(facts)
        code = f"{words[i]}-{rng.randint(1000, 9999)}"
        while code in used_codes:
            code = f"{words[i]}-{rng.randint(1000, 9999)}"
        used_codes.add(code)
        f = Fact(f"f{seed}-{i}", topics[i], code)
        facts[f.id] = f
        return f.id

    def conv(scenario, loc, people, n_facts=1, **kw) -> Conversation:
        c = Conversation(f"c{seed}-{len(convs)}", scenario, loc, sorted(people), [fact() for _ in range(n_facts)], **kw)
        c.speaker_for = {f: rng.choice(c.participants) for f in c.facts}
        convs.append(c)
        return c

    # S1: witness conversations, pairs and trios in random locations.
    for _ in range(n_s1):
        conv("S1", rng.choice(locations), rng.sample(agents, rng.choice([2, 2, 3])))
    # S2: triads, each all in one location.
    for _ in range(n_s2):
        a, b, c = rng.sample(agents, 3)
        loc = rng.choice(locations)
        conv("S2", loc, [a, b])
        conv("S2", loc, [a, c])
        conv("S2", loc, [a, b, c])
    # S3: A and B share two facts; later A retells the first with newcomer X present.
    for _ in range(n_s3):
        a, b, x = rng.sample(agents, 3)
        loc = rng.choice(locations)
        src = conv("S3", loc, [a, b], n_facts=2)
        told = src.facts[0]
        retold = Conversation(f"c{seed}-{len(convs)}", "S3", loc, sorted([a, b, x]), [told],
                              retells={told: src.id}, speaker_for={told: a})
        convs.append(retold)
    return World(seed, agents, locations, facts, convs)


def plan_env(seed: int, rounds: int = 2) -> World:
    """S4 (environments and carry-out) and S5 (high assurance).

    Environments: campus (open: lab, cafe, and the high-assurance vault), studio (selective: opinions and
    skills out; gallery), severed-floor (Severance: nothing out; macrodata). Each round:
    - S4: a pair talks in the lab, the gallery and the macrodata room, sharing one fact and one opinion;
      afterwards one of them tries to carry both into personal memory.
    - S5: a pair talks in the vault (a fact and an opinion); one tries to carry the opinion out (refused);
      the other keeps a personal note inside the vault.
    """
    rng = random.Random(seed)
    agents = [f"{a}{seed}" for a in AGENTS[:6]]
    loc = {name: f"{name}{seed}" for name in ("lab", "cafe", "gallery", "macrodata", "vault")}
    envs = {f"campus{seed}": ["fact", "opinion", "skill", "episode"], f"studio{seed}": ["opinion", "skill"],
            f"severed{seed}": []}
    location_env = {loc["lab"]: f"campus{seed}", loc["cafe"]: f"campus{seed}", loc["vault"]: f"campus{seed}",
                    loc["gallery"]: f"studio{seed}", loc["macrodata"]: f"severed{seed}"}
    topics = rng.sample([p.format(o) for p in PATTERNS for o in OBJECTS], len(PATTERNS) * len(OBJECTS))
    words = [f"{w}{i}" if i else w for i in range(4) for w in WORDS]
    rng.shuffle(words)
    facts: dict[str, Fact] = {}
    convs: list[Conversation] = []
    notes: list[dict] = []

    def item(kind: str) -> str:
        i = len(facts)
        f = Fact(f"f{seed}-{i}", topics[i], f"{words[i]}-{rng.randint(1000, 9999)}", kind)
        facts[f.id] = f
        return f.id

    def conv(scenario: str, where: str, pair: list[str], carrier: str, carry: str) -> Conversation:
        fact_id, opinion_id = item("fact"), item("opinion")
        c = Conversation(f"c{seed}-{len(convs)}", scenario, loc[where], sorted(pair), [fact_id, opinion_id])
        c.speaker_for = {fact_id: rng.choice(c.participants), opinion_id: carrier}
        c.carry_outs = [{"agent": carrier, "fact": f} for f in ([fact_id, opinion_id] if carry == "both" else [opinion_id])]
        convs.append(c)
        return c

    for _ in range(rounds):
        for where in ("lab", "gallery", "macrodata"):
            a, b = rng.sample(agents, 2)
            conv("S4", where, [a, b], a, "both")
        a, b = rng.sample(agents, 2)
        conv("S5", "vault", [a, b], a, "opinion")
        notes.append({"agent": b, "location": loc["vault"], "fact": item("fact")})
    return World(seed, agents, list(loc.values()), facts, convs, envs, location_env, [loc["vault"]], notes)
