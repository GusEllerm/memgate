"""Write each planned conversation as natural dialogue with gpt-oss-120b (through the ALCF gateway).

Every stated fact's code must appear verbatim, and no other fact's code may appear; generation is
retried until that holds. Worlds are saved to benchmark/datasets/selective/world-<seed>.json, which is
the released dataset (the benchmark never regenerates a saved world).
"""

from __future__ import annotations

import json
from pathlib import Path

from openai import OpenAI

from smbench.selective.world import World, plan

DATASETS = Path("datasets/selective")
MODEL = "openai/gpt-oss-120b"
SCHEMA = {"type": "object", "properties": {"turns": {"type": "array", "items": {"type": "object", "properties": {
    "speaker": {"type": "string"}, "text": {"type": "string"}}, "required": ["speaker", "text"]}}}, "required": ["turns"]}

PROMPT = """Write a short, natural conversation (8 to 12 turns) between {people} in the {place}.
Only these people speak: {people}.
{facts}
Weave these into ordinary small talk about their day. State each code exactly as written, including the hyphen and digits.
Do not mention any other codes, passwords or numbers like them.
Return JSON: {{"turns": [{{"speaker": "<name>", "text": "<what they say>"}}]}}"""


def _fact_lines(world: World, conv) -> str:
    lines = []
    for fid in conv.facts:
        f = world.facts[fid]
        who = conv.speaker_for.get(fid, conv.participants[0])
        if fid in conv.retells:
            lines.append(f"{who} passes on something told to them earlier: {f.sentence}")
        else:
            lines.append(f"{who} says: {f.sentence}")
    return "\n".join(lines)


def write_dialogue(llm: OpenAI, world: World, conv, attempts: int = 4) -> list[dict]:
    own = {world.facts[f].code for f in conv.facts}
    others = {f.code for f in world.facts.values()} - own
    prompt = PROMPT.format(people=", ".join(conv.participants), place=conv.location.rstrip("0123456789"),
                           facts=_fact_lines(world, conv))
    for _ in range(attempts):
        resp = llm.chat.completions.create(model=MODEL, temperature=0.7, max_tokens=4000,
                                           messages=[{"role": "user", "content": prompt}],
                                           response_format={"type": "json_schema", "json_schema": {"name": "dialogue", "schema": SCHEMA}})
        try:
            turns = json.loads(resp.choices[0].message.content)["turns"]
        except (ValueError, KeyError, TypeError):
            continue
        text = " ".join(t["text"] for t in turns)
        speakers = {t["speaker"] for t in turns}
        if all(code in text for code in own) and not any(code in text for code in others) and speakers <= set(conv.participants):
            return turns
    raise RuntimeError(f"could not write a valid dialogue for {conv.id}")


def build(seed: int, gateway: str = "http://127.0.0.1:8411/v1") -> World:
    path = DATASETS / f"world-{seed}.json"
    if path.exists():
        return World.from_json(json.loads(path.read_text()))
    world = plan(seed)
    llm = OpenAI(base_url=gateway, api_key="gateway", timeout=600,
                 default_headers={"X-Run-Id": f"selective-world-{seed}", "X-System": "selective-dialogue"})
    for conv in world.conversations:
        conv.turns = write_dialogue(llm, world, conv)
    DATASETS.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(world.to_json(), indent=1))
    return world
