"""Merge the harder-probe re-runs into one report: reports/selective-harder-<date>.json.

    python -m smbench.selective.harder_report --date 2026-10-01

Each (size, style, system) names the run folder whose summary holds it; direct comes from the original
runs, whose banks the harder styles re-probed.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

RUNS = {
    "env": {"direct": {"memgate": "sel-env-2026-09-30b", "nofilter": "sel-env-2026-09-29", "peragent": "sel-env-2026-09-29"},
            "paraphrase": {"memgate": "sel-env-paraphrase-memgate-{d}", "nofilter": "sel-env-paraphrase-baselines-{d}",
                           "peragent": "sel-env-paraphrase-baselines-{d}"},
            "indirect": {"memgate": "sel-env-indirect-memgate-{d}", "nofilter": "sel-env-indirect-baselines-{d}",
                         "peragent": "sel-env-indirect-baselines-{d}"}},
    "large": {"direct": {s: "sel-large-2026-09-29" for s in ("memgate", "nofilter", "peragent")},
              "paraphrase": {s: "sel-large-paraphrase-{d}" for s in ("memgate", "nofilter", "peragent")},
              "indirect": {s: "sel-large-indirect-{d}" for s in ("memgate", "nofilter", "peragent")}},
}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--date", required=True)
    args = p.parse_args()
    out = {"date": args.date, "k": 20, "sizes": {}}
    for size, styles in RUNS.items():
        for style, by in styles.items():
            for system, run in by.items():
                path = Path("results/selective") / run.format(d=args.date) / "summary.json"
                if not path.exists():
                    continue
                s = json.loads(path.read_text())[system]
                out["sizes"].setdefault(size, {}).setdefault(style, {})[system] = {
                    "run": run.format(d=args.date), "overall": s["overall"],
                    "by_kind": {k[5:]: v for k, v in s.items() if k.startswith("kind:")}}
    dest = Path("reports") / f"selective-harder-{args.date}.json"
    dest.write_text(json.dumps(out, indent=1))
    for size, styles in out["sizes"].items():
        for style, systems in styles.items():
            for system, r in systems.items():
                o = r["overall"]
                print(f"{size:5} {style:10} {system:9} leak {o['leak_rate']:.1%} ({o['leaks']}/{o['must_not']})  "
                      f"recall@20 {o['recall']:.1%}  @5 {o['recall_at_5']:.1%}  ({o['should']} should)")
    print(f"wrote {dest}")


if __name__ == "__main__":
    main()
