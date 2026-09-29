"""Live progress for LoCoMo runs: per-conversation progress, running accuracy, gateway load.

    uv run python -m smbench.locomo.watch full-2026-09-28          # refreshes every 10 s; Ctrl-C to stop
    uv run python -m smbench.locomo.watch full-2026-09-28 --once   # print once
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.request
from pathlib import Path

from smbench.locomo import data

RESULTS = Path("results/locomo")


def _totals() -> dict[str, tuple[int, int]]:
    return {s["sample_id"]: (len(data.sessions(s)), len(data.questions(s))) for s in data.load()}


def _gateway(url: str) -> dict | None:
    try:
        with urllib.request.urlopen(f"{url}/health", timeout=3) as r:
            return json.loads(r.read())
    except OSError:
        return None


def _tail_error(log: Path) -> str:
    if not log.exists():
        return ""
    lines = [l for l in log.read_text(errors="replace").splitlines()[-40:] if "Error" in l or "Traceback" in l]
    return lines[-1][:90] if lines else ""


def render(prefix: str, gateway: str, started: float, totals: dict, systems=("hindsight", "mem0")) -> str:
    out = [f"LoCoMo run {prefix!r}   {time.strftime('%H:%M:%S')}   elapsed {int(time.time() - started) // 60} min", ""]
    g = _gateway(gateway)
    out.append("gateway: " + (f"{g['in_flight']}/{g['max_concurrency']} in flight, {g['waiting']} queued, "
                              f"{g['completed']} done, {g['failed']} failed" if g else "NOT REACHABLE"))
    out.append("")
    grand: dict[str, list[int]] = {}
    for system in systems:
        rows = []
        for conv, (n_sess, n_q) in totals.items():
            d = RESULTS / f"{prefix}-{system}-{conv}"
            if not d.exists():
                rows.append(f"  {conv:8} waiting")
                continue
            state = json.loads((d / "state.json").read_text()) if (d / "state.json").exists() else {}
            ingested = len(state.get("ingested", {}).get(conv, []))
            answers = [json.loads(l) for l in (d / "answers.jsonl").read_text().splitlines()] if (d / "answers.jsonl").exists() else []
            judged = [a for a in answers if a.get("label")]
            correct = sum(a["label"] == "CORRECT" for a in judged)
            acc = f"{correct / len(judged):6.1%}" if judged else "     -"
            done = (d / "summary.json").exists()
            status = "done" if done else ("answering" if answers or ingested == n_sess else "ingesting")
            err = _tail_error(Path("results/logs") / f"{prefix}-{system}-{conv}.log")
            rows.append(f"  {conv:8} {status:9} sessions {ingested:2}/{n_sess:2}  questions {len(answers):3}/{n_q:3}  acc {acc}"
                        + (f"  ! {err}" if err and not done else ""))
            t = grand.setdefault(system, [0, 0, 0, 0])
            t[0] += ingested; t[1] += len(answers); t[2] += correct; t[3] += len(judged)
        t = grand.get(system, [0, 0, 0, 0])
        all_s = sum(v[0] for v in totals.values()); all_q = sum(v[1] for v in totals.values())
        acc = f"{t[2] / t[3]:.1%}" if t[3] else "-"
        out.append(f"{system}: sessions {t[0]}/{all_s}, questions {t[1]}/{all_q}, accuracy so far {acc}")
        out += rows
        out.append("")
    return "\n".join(out)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("prefix", help="run-id prefix given to scripts/run_locomo_full.sh")
    p.add_argument("--gateway", default="http://127.0.0.1:8411")
    p.add_argument("--every", type=float, default=10)
    p.add_argument("--once", action="store_true")
    p.add_argument("--systems", nargs="+", default=["hindsight", "mem0"])
    args = p.parse_args()
    totals, started = _totals(), time.time()
    if args.once:
        print(render(args.prefix, args.gateway, started, totals, args.systems))
        return
    try:
        while True:
            print("\033[2J\033[H" + render(args.prefix, args.gateway, started, totals, args.systems), flush=True)
            time.sleep(args.every)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
