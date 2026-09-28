"""Build the benchmark results page.

    uv run python -m smbench.site.build        # writes site/build/smbench.html

Inputs: site/registry.json (systems, benchmarks, runs, published results, protocol, findings) and
the run reports it names (reports/*.json). Output: one HTML file with the data embedded, published
as the benchmark artifact. To add a memory system or benchmark, edit the registry; to add results,
add a report and a run entry; then rebuild and republish to the same artifact URL.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

SITE = Path("site")
TEMPLATE = SITE / "template.html"
OUT = SITE / "build" / "smbench.html"


def wilson(acc: float, n: int, z: float = 1.96) -> list[float]:
    if not n:
        return [0.0, 0.0]
    d = 1 + z * z / n
    c = acc + z * z / (2 * n)
    r = z * math.sqrt(acc * (1 - acc) / n + z * z / (4 * n * n))
    return [round((c - r) / d, 4), round((c + r) / d, 4)]


def _score(s: dict) -> dict:
    acc, n = s.get("judge_accuracy"), s.get("n", 0)
    return {"acc": acc, "n": n, "f1": s.get("f1"), "ci": s.get("ci95") or (wilson(acc, n) if acc is not None else None)}


def normalise(run: dict, benchmark: dict) -> dict:
    report = json.loads(Path(run["report"]).read_text())
    by_name = {c["name"].lower(): str(c["id"]) for c in benchmark.get("categories", [])}
    if run["format"] == "aggregate":
        systems = {sid: (v["scores"], v.get("per_conversation", {})) for sid, v in report["systems"].items()}
        paired = report.get("paired")
    elif run["format"] == "pilot":
        systems = {sid: (report[sid]["scores"], {}) for sid in ("hindsight", "mem0") if sid in report}
        p = report.get("paired", {})
        paired = {"systems": ["hindsight", "mem0"], "only_first_correct": p.get("hindsight_only_correct"),
                  "only_second_correct": p.get("mem0_only_correct"), "mcnemar_p": p.get("mcnemar_exact_p")}
    else:
        raise ValueError(f"unknown report format {run['format']!r} for run {run['id']}")
    out = {}
    for sid, (scores, per_conv) in systems.items():
        cats = {by_name[k]: _score(v) for k, v in scores.items() if k in by_name}
        out[sid] = {"overall": _score(scores["overall"]), "categories": cats, "per_conversation": per_conv}
    return {"systems": out, "paired": paired}


def build() -> Path:
    registry = json.loads((SITE / "registry.json").read_text())
    benchmarks = {b["id"]: b for b in registry["benchmarks"]}
    results = {r["id"]: normalise(r, benchmarks[r["benchmark"]]) for r in registry["runs"] if r.get("report")}
    data = {**registry, "results": results}
    html = TEMPLATE.read_text().replace("__DATA__", json.dumps(data).replace("</", "<\\/"))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html)
    return OUT


if __name__ == "__main__":
    print(f"wrote {build()}")
