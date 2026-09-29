"""Re-grade existing LoCoMo answers with a different judge model (no re-ingest, no re-answering).

    uv run python -m smbench.locomo.regrade full-2026-09-28 --judge openai/gpt-oss-120b

For every run directory matching <prefix>-<system>-conv-*, reads answers.jsonl and writes
answers.judge-<judge-slug>.jsonl with the new label, then prints accuracy per system under both
judges and their agreement. Used to measure how much a score depends on the judge.
"""

from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from openai import OpenAI

from smbench.locomo.prompts import JUDGE, JUDGE_LENIENT
from smbench.locomo.run import GATEWAY, _json_label

PROMPTS = {"strict": JUDGE, "lenient": JUDGE_LENIENT}

RESULTS = Path("results/locomo")


def slug(model: str) -> str:
    return model.split("/")[-1]


def grade(llm: OpenAI, judge: str, row: dict, prompt: str = JUDGE, attempts: int = 3) -> dict:
    text = ""
    for _ in range(attempts):
        text = llm.chat.completions.create(
            model=judge, temperature=0, max_tokens=4000,
            messages=[{"role": "user", "content": prompt.format(question=row["question"], gold=row["gold"], answer=row["answer"])}],
        ).choices[0].message.content or ""
        label = _json_label(text)
        if label:
            return {**row, "label": label, "judge_raw": text[:500]}
    return {**row, "label": None, "judge_raw": text[:500]}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("prefix")
    p.add_argument("--judge", required=True)
    p.add_argument("--prompt", choices=sorted(PROMPTS), default="strict",
                   help="strict = our judge prompt; lenient = Hindsight's paper-era LoCoMo judge prompt")
    p.add_argument("--workers", type=int, default=6)
    p.add_argument("--gateway", default=GATEWAY)
    args = p.parse_args()

    llm = OpenAI(base_url=args.gateway, api_key="gateway", timeout=600, max_retries=2,
                 default_headers={"X-Run-Id": f"{args.prefix}-regrade-{slug(args.judge)}", "X-System": "locomo-regrade"})
    totals: dict[str, dict] = {}
    for d in sorted(RESULTS.glob(f"{args.prefix}-*-conv-*")):
        system = d.name[len(args.prefix) + 1:].split("-conv-")[0]
        suffix = slug(args.judge) + ("" if args.prompt == "strict" else f"-{args.prompt}")
        out = d / f"answers.judge-{suffix}.jsonl"
        rows = [json.loads(l) for l in (d / "answers.jsonl").read_text().splitlines()]
        done = {json.loads(l)["index"] for l in out.read_text().splitlines()} if out.exists() else set()
        todo = [r for r in rows if r["index"] not in done]
        with ThreadPoolExecutor(args.workers) as pool, out.open("a") as f:
            for new in pool.map(lambda r: grade(llm, args.judge, r, PROMPTS[args.prompt]), todo):
                f.write(json.dumps(new) + "\n")
                f.flush()
        regraded = {json.loads(l)["index"]: json.loads(l)["label"] for l in out.read_text().splitlines()}
        t = totals.setdefault(system, {"n": 0, "orig": 0, "new": 0, "agree": 0, "unjudged": 0})
        for r in rows:
            new = regraded.get(r["index"])
            t["n"] += 1
            t["orig"] += r["label"] == "CORRECT"
            t["new"] += new == "CORRECT"
            t["agree"] += new == r["label"]
            t["unjudged"] += new is None
        print(f"{d.name}: {len(todo)} regraded", flush=True)
    for system, t in totals.items():
        print(f"{system}: n={t['n']} original judge {t['orig'] / t['n']:.1%}, {args.judge} ({args.prompt}) {t['new'] / t['n']:.1%}, "
              f"agreement {t['agree'] / t['n']:.1%}, unjudged {t['unjudged']}")


if __name__ == "__main__":
    main()
