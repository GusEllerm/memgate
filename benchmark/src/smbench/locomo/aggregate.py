"""Combine per-conversation LoCoMo runs into one report.

    uv run python -m smbench.locomo.aggregate full-2026-09-28 --systems hindsight mem0 \
        --repeat conv-26:pilot-conv26 --out reports/locomo-full-2026-09-28.json

Reports, per system: judge accuracy with a 95% Wilson interval and token F1, overall and per
category; per-conversation accuracy; ingest and question timings. Across systems: an exact
McNemar test on paired questions, for every pair of systems. A system may be given as
SYSTEM@PREFIX to take it from another run (e.g. hindsight@full-2026-09-28). `--repeat CONV:PREFIX`
compares a conversation with an earlier run of it (run-to-run variance).
"""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path

from smbench.locomo.data import CATEGORIES
from smbench.locomo.metrics import summarise

RESULTS = Path("results/locomo")


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    r = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return round((c - r) / d, 4), round((c + r) / d, 4)


def mcnemar(b: int, c: int) -> float:
    n = b + c
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, k) for k in range(0, min(b, c) + 1)) / 2**n
    return round(min(1.0, 2 * tail), 4)


def load_runs(prefix: str, system: str) -> tuple[list[dict], dict]:
    rows, timings = [], {}
    for d in sorted(RESULTS.glob(f"{prefix}-{system}-conv-*")):
        rows += [json.loads(l) for l in (d / "answers.jsonl").read_text().splitlines()]
        state = json.loads((d / "state.json").read_text())
        timings.update(state.get("timings", {}))
    return rows, timings


def system_report(rows: list[dict], timings: dict) -> dict:
    scores = summarise(rows)
    for name, s in scores.items():
        group = rows if name == "overall" else [r for r in rows if CATEGORIES.get(r["category"]) == name]
        judged = [r for r in group if r.get("label")]
        s["ci95"] = wilson(sum(r["label"] == "CORRECT" for r in judged), len(judged))
    per_conv = defaultdict(list)
    for r in rows:
        per_conv[r["conversation_id"]].append(r)
    conv = {c: round(sum(r["label"] == "CORRECT" for r in rs if r.get("label")) / max(1, sum(bool(r.get("label")) for r in rs)), 4)
            for c, rs in sorted(per_conv.items())}
    ingest = sum(sum(t.get("sessions", {}).values()) + t.get("finalize_s", 0) for t in timings.values())
    questions = sum(t.get("questions_s", 0) for t in timings.values())
    return {"scores": scores, "per_conversation": conv,
            "timing_s": {"ingest_process_total": round(ingest), "questions_process_total": round(questions)}}


def paired(a: list[dict], b: list[dict]) -> dict:
    ka = {(r["conversation_id"], r["index"]): r.get("label") for r in a}
    kb = {(r["conversation_id"], r["index"]): r.get("label") for r in b}
    keys = [k for k in ka if ka[k] and kb.get(k)]
    only_a = sum(ka[k] == "CORRECT" and kb[k] == "WRONG" for k in keys)
    only_b = sum(ka[k] == "WRONG" and kb[k] == "CORRECT" for k in keys)
    return {"n": len(keys), "only_first_correct": only_a, "only_second_correct": only_b, "mcnemar_p": mcnemar(only_a, only_b)}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("prefix")
    p.add_argument("--systems", nargs="+", default=["hindsight", "mem0"])
    p.add_argument("--repeat", action="append", default=[], help="CONV:PREFIX of an earlier run of one conversation")
    p.add_argument("--out", type=Path)
    args = p.parse_args()

    runs = {s: load_runs(*(s.split("@")[::-1] if "@" in s else (args.prefix, s))) for s in args.systems}
    report = {"prefix": args.prefix, "systems": {s: system_report(*runs[s]) for s in args.systems}}
    pairs = [(a, b) for i, a in enumerate(args.systems) for b in args.systems[i + 1:]]
    if len(pairs) == 1:
        a, b = pairs[0]
        report["paired"] = {"systems": [a, b], **paired(runs[a][0], runs[b][0])}
    elif pairs:
        report["paired"] = [{"systems": [a, b], **paired(runs[a][0], runs[b][0])} for a, b in pairs]
    repeats = {}
    for spec in args.repeat:
        conv, old_prefix = spec.split(":")
        for s in args.systems:
            old_dir = RESULTS / f"{old_prefix}-{s}"
            if not (old_dir / "answers.jsonl").exists():
                continue
            old = [json.loads(l) for l in (old_dir / "answers.jsonl").read_text().splitlines()]
            new = [r for r in runs[s][0] if r["conversation_id"] == conv]
            acc = lambda rs: round(sum(r["label"] == "CORRECT" for r in rs if r.get("label")) / max(1, len(rs)), 4)
            repeats[f"{s}:{conv}"] = {"earlier": acc(old), "now": acc(new), **paired(old, new)}
    if repeats:
        report["run_to_run"] = repeats
    text = json.dumps(report, indent=1)
    if args.out:
        args.out.write_text(text)
    print(text)


if __name__ == "__main__":
    main()
