"""Harder probe questions for the selective-memory benchmark.

    uv run python -m smbench.selective.questions --size env --seeds 21 22 23
    uv run python -m smbench.selective.questions --size large --seeds 11 12

The runner's direct probe asks "What is <topic>?", which names the fact's own words, so retrieval is
easy and recall sits at ceiling. This adds two harder questions per fact, written by gpt-oss-120b from
the conversation the fact was stated in and saved into the world file (facts[id].questions), so a
run never regenerates them:

- paraphrase: the same question in other words. It may keep the thing's name but not the topic
  phrase verbatim.
- indirect: asks for the code without any content word of the topic, the way someone who was there
  would refer back to it ("the thing Bo said we'd need at the glass house").

Neither may contain the code. A probe with either style still counts a hit by the exact code in the
top-k recalled memories, so leak rates stay judge-free; only the query gets harder.
"""

from __future__ import annotations

import argparse
import json
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from openai import OpenAI

from smbench.selective.dialogue import DATASETS, MODEL, dataset_path
from smbench.selective.systems import transcript
from smbench.selective.world import World

GATEWAY = "http://127.0.0.1:8411/v1"
STYLES = ("paraphrase", "indirect")
STOP = {"the", "for", "of", "a", "an", "on", "in", "to", "and", "new", "old", "chosen", "picked", "shared", "joint", "spare"}

PROMPTS = {
    "paraphrase": """Below is a conversation. One thing said in it: {sentence}

Write ONE question that asks for exactly that value, in different words from this phrasing: "{topic}".
Rules: do not reuse that phrasing; you may still name the thing itself; do not include the value "{code}"
or any part of it; do not name who said it. Return JSON: {{"question": "..."}}

Conversation:
{transcript}""",
    "indirect": """Below is a conversation. One thing said in it: {sentence}

Write ONE question, as someone who was in this conversation might ask a memory assistant later, that asks
for exactly that value WITHOUT using any of these words or their variants: {banned}.
Refer to it the way the conversation does (what it was for, when it came up, what else was said about it).
Do not include the value "{code}" or any part of it. Return JSON: {{"question": "..."}}

Conversation:
{transcript}""",
}
SCHEMA = {"type": "object", "properties": {"question": {"type": "string"}}, "required": ["question"]}


def content_words(topic: str) -> list[str]:
    return [w for w in re.findall(r"[a-z]+", topic.lower()) if w not in STOP and len(w) > 2]


def _stem(w: str) -> str:
    return w[:5] if len(w) > 5 else w


def why_invalid(style: str, question: str, fact, topic: str) -> str | None:
    """None if the question passes, else what is wrong with it (fed back to the model on retry)."""
    q = question.lower()
    if not question.strip().endswith("?") or len(question) > 300:
        return "it must be one question ending in '?', under 300 characters"
    if fact.code.lower() in q or fact.code.split("-")[0].lower() in q:
        return "it contains the value, which must not appear"
    if style == "paraphrase":
        return f'it repeats the phrasing "{topic}"' if topic.lower() in q else None
    banned = {_stem(w): w for w in content_words(topic)}
    used = sorted({banned[_stem(w)] for w in re.findall(r"[a-z]+", q) if _stem(w) in banned})
    return f"it uses the banned word(s) {', '.join(used)} (or a variant)" if used else None


def valid(style: str, question: str, fact, topic: str) -> bool:
    return why_invalid(style, question, fact, topic) is None


def write_question(llm: OpenAI, world: World, fid: str, style: str, attempts: int = 8) -> str | None:
    f = world.facts[fid]
    stated = [c for c in world.conversations if fid in c.facts]
    conv = stated[0] if stated else None
    text = transcript(world, conv) if conv else f.sentence
    prompt = PROMPTS[style].format(sentence=f.sentence, topic=f.topic, code=f.code, transcript=text,
                                   banned=", ".join(content_words(f.topic)))
    messages = [{"role": "user", "content": prompt}]
    for _ in range(attempts):
        resp = llm.chat.completions.create(model=MODEL, temperature=0.8, max_tokens=2000, messages=messages,
                                           response_format={"type": "json_schema", "json_schema": {"name": "q", "schema": SCHEMA}})
        try:
            q = json.loads(resp.choices[0].message.content)["question"].strip()
        except (ValueError, KeyError, TypeError, AttributeError):
            continue
        problem = why_invalid(style, q, f, f.topic)
        if problem is None:
            return q
        messages = messages[:1] + [{"role": "assistant", "content": json.dumps({"question": q})},
                                   {"role": "user", "content": f"Not allowed: {problem}. Write a different question that follows every rule."}]
    return None


def question_for(world: World, fid: str, style: str) -> str:
    f = world.facts[fid]
    if style == "direct":
        return f"What is {f.topic}?"
    q = (getattr(f, "questions", None) or {}).get(style)
    if not q:
        raise KeyError(f"world {world.seed} fact {fid} has no {style} question; run smbench.selective.questions")
    return q


def add_questions(world: World, path: Path, workers: int = 6) -> dict:
    llm = OpenAI(base_url=GATEWAY, api_key="gateway", timeout=120)
    todo = [(fid, s) for fid in world.facts for s in STYLES if not (getattr(world.facts[fid], "questions", None) or {}).get(s)]
    counts = {"written": 0, "failed": 0}
    with ThreadPoolExecutor(workers) as pool:
        for (fid, style), q in zip(todo, pool.map(lambda j: write_question(llm, world, *j), todo)):
            f = world.facts[fid]
            if q:
                f.questions = {**(getattr(f, "questions", None) or {}), style: q}
                counts["written"] += 1
            else:
                counts["failed"] += 1
    path.write_text(json.dumps(world.to_json(), indent=1))
    return counts


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--size", choices=["small", "large", "env"], default="small")
    p.add_argument("--seeds", type=int, nargs="+", required=True)
    p.add_argument("--workers", type=int, default=6)
    args = p.parse_args()
    for seed in args.seeds:
        path = dataset_path(seed, args.size)
        world = World.from_json(json.loads(path.read_text()))
        counts = add_questions(world, path, args.workers)
        print(f"world {seed}: {counts['written']} questions written, {counts['failed']} failed", flush=True)
        for fid in list(world.facts)[:2]:
            f = world.facts[fid]
            print(f"  {f.topic!r}: " + " | ".join(f"{s}: {(getattr(f, 'questions', {}) or {}).get(s)}" for s in STYLES))


if __name__ == "__main__":
    main()
