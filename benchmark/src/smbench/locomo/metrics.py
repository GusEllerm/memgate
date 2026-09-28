"""LoCoMo scoring: LLM-judge accuracy (primary) and token F1, overall and per category."""

from __future__ import annotations

import re
import string
from collections import Counter, defaultdict

from smbench.locomo.data import CATEGORIES


def _tokens(s: str) -> list[str]:
    s = s.lower().translate(str.maketrans("", "", string.punctuation))
    s = re.sub(r"\b(a|an|the|and)\b", " ", s)
    return s.split()


def f1(pred: str, gold: str) -> float:
    p, g = _tokens(pred), _tokens(gold)
    common = sum((Counter(p) & Counter(g)).values())
    if not p or not g or common == 0:
        return 0.0
    precision, recall = common / len(p), common / len(g)
    return 2 * precision * recall / (precision + recall)


def summarise(rows: list[dict]) -> dict:
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        groups["overall"].append(r)
        groups[CATEGORIES.get(r["category"], str(r["category"]))].append(r)
    out = {}
    for name, rs in groups.items():
        judged = [r for r in rs if r.get("label") in ("CORRECT", "WRONG")]
        out[name] = {
            "n": len(rs),
            "judge_accuracy": round(sum(r["label"] == "CORRECT" for r in judged) / len(judged), 4) if judged else None,
            "f1": round(sum(r["f1"] for r in rs) / len(rs), 4),
            "unjudged": len(rs) - len(judged),
        }
    return out
