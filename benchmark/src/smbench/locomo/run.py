"""Run LoCoMo against one memory system.

    uv run python -m smbench.locomo.run --system hindsight --conversations conv-26 --run-id pilot-hs-1

Phases, all resumable from results/locomo/<run-id>/:
1. ingest: store every session of each conversation (progress in state.json);
2. finalize: wait for the system's background processing;
3. questions: retrieve k memories, answer with the answer model, grade with the judge model,
   one JSON line per question in answers.jsonl;
4. summary.json: judge accuracy and token F1, overall and per category, plus timings.

All LLM calls (the memory system's own, answers and judging) go through the ALCF gateway.
"""

from __future__ import annotations

import argparse
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from openai import OpenAI

from smbench.adapters import load_adapter
from smbench.locomo import data
from smbench.locomo.metrics import f1, summarise
from smbench.locomo.prompts import ANSWER, JUDGE

GATEWAY = "http://127.0.0.1:8411/v1"
ANSWER_MODEL = "openai/gpt-oss-120b"
JUDGE_MODEL = "nemotron-3-ultra"


def _json_label(text: str) -> str | None:
    m = re.search(r"\{.*\}", text or "", re.S)
    if m:
        try:
            label = str(json.loads(m.group(0)).get("label", "")).upper()
            if label in ("CORRECT", "WRONG"):
                return label
        except ValueError:
            pass
    upper = (text or "").upper()
    if "CORRECT" in upper and "WRONG" not in upper:
        return "CORRECT"
    if "WRONG" in upper and "CORRECT" not in upper:
        return "WRONG"
    return None


class Runner:
    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.out = Path("results/locomo") / args.run_id
        self.out.mkdir(parents=True, exist_ok=True)
        self.state_path = self.out / "state.json"
        self.state = json.loads(self.state_path.read_text()) if self.state_path.exists() else {"ingested": {}, "timings": {}}
        self.adapter = load_adapter(args.system, args.run_id, args.gateway, args.model)
        headers = {"X-Run-Id": args.run_id, "X-System": f"locomo-{args.system}"}
        self.llm = OpenAI(base_url=args.gateway, api_key="gateway", timeout=600, default_headers=headers, max_retries=2)

    def _save_state(self) -> None:
        self.state_path.write_text(json.dumps(self.state, indent=1))

    def ingest(self, sample: dict) -> None:
        cid = sample["sample_id"]
        done = set(self.state["ingested"].get(cid, []))
        for s in data.sessions(sample)[: self.args.max_sessions or None]:
            if s.index in done:
                continue
            t0 = time.monotonic()
            self.adapter.ingest_session(s)
            dt = round(time.monotonic() - t0, 2)
            done.add(s.index)
            self.state["ingested"][cid] = sorted(done)
            self.state["timings"].setdefault(cid, {}).setdefault("sessions", {})[str(s.index)] = dt
            self._save_state()
            print(f"  ingested {cid} session {s.index} ({len(s.turns)} turns) in {dt}s", flush=True)
        t0 = time.monotonic()
        self.adapter.finalize(cid)
        self.state["timings"][cid]["finalize_s"] = round(time.monotonic() - t0, 2)
        self._save_state()

    def _ask(self, sample: dict, q: data.Question) -> dict:
        conv = sample["conversation"]
        t0 = time.monotonic()
        mems = self.adapter.search(q.conversation_id, q.question, self.args.k)
        t_search = time.monotonic() - t0
        prompt = ANSWER.format(speakers=f"{conv['speaker_a']} and {conv['speaker_b']}",
                               memories="\n".join(m.render() for m in mems) or "(none)", question=q.question)
        t1 = time.monotonic()
        answer = self.llm.chat.completions.create(model=self.args.model, messages=[{"role": "user", "content": prompt}],
                                                  temperature=0, max_tokens=4000).choices[0].message.content or ""
        t_answer = time.monotonic() - t1
        t2 = time.monotonic()
        judged = self.llm.chat.completions.create(
            model=self.args.judge, temperature=0, max_tokens=2000,
            messages=[{"role": "user", "content": JUDGE.format(question=q.question, gold=q.answer, answer=answer.strip())}],
        ).choices[0].message.content
        return {
            "conversation_id": q.conversation_id, "index": q.index, "category": q.category,
            "question": q.question, "gold": q.answer, "answer": answer.strip(),
            "label": _json_label(judged), "judge_raw": (judged or "")[:500], "f1": round(f1(answer, q.answer), 4),
            "retrieved": [m.render() for m in mems],
            "search_s": round(t_search, 3), "answer_s": round(t_answer, 3), "judge_s": round(time.monotonic() - t2, 3),
        }

    def questions(self, sample: dict) -> None:
        path = self.out / "answers.jsonl"
        seen = set()
        if path.exists():
            seen = {(r["conversation_id"], r["index"]) for r in map(json.loads, path.read_text().splitlines())}
        todo = [q for q in data.questions(sample) if (q.conversation_id, q.index) not in seen]
        if self.args.max_questions:
            todo = todo[: max(0, self.args.max_questions - len(seen))]
        t0 = time.monotonic()
        with ThreadPoolExecutor(self.args.workers) as pool, path.open("a") as f:
            for n, row in enumerate(pool.map(lambda q: self._ask(sample, q), todo), 1):
                f.write(json.dumps(row) + "\n")
                f.flush()
                if n % 10 == 0 or n == len(todo):
                    print(f"  {sample['sample_id']}: {n}/{len(todo)} questions, {time.monotonic() - t0:.0f}s", flush=True)
        self.state["timings"].setdefault(sample["sample_id"], {})["questions_s"] = round(time.monotonic() - t0, 2)
        self._save_state()

    def summary(self) -> dict:
        rows = [json.loads(l) for l in (self.out / "answers.jsonl").read_text().splitlines()]
        summary = {"run_id": self.args.run_id, "system": self.adapter.describe(), "answer_model": self.args.model,
                   "judge_model": self.args.judge, "k": self.args.k, "scores": summarise(rows),
                   "timings": self.state["timings"]}
        (self.out / "summary.json").write_text(json.dumps(summary, indent=1))
        return summary


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--system", required=True, choices=["hindsight", "mem0"])
    p.add_argument("--run-id", required=True)
    p.add_argument("--conversations", nargs="*", help="sample ids, e.g. conv-26 (default: all)")
    p.add_argument("--k", type=int, default=20, help="memories retrieved per question")
    p.add_argument("--workers", type=int, default=6, help="parallel questions (the gateway still caps ALCF at 6)")
    p.add_argument("--max-questions", type=int, default=0, help="stop after this many questions per run (0 = all)")
    p.add_argument("--max-sessions", type=int, default=0, help="ingest only the first N sessions (smoke tests)")
    p.add_argument("--skip-ingest", action="store_true")
    p.add_argument("--gateway", default=GATEWAY)
    p.add_argument("--model", default=ANSWER_MODEL)
    p.add_argument("--judge", default=JUDGE_MODEL)
    args = p.parse_args()

    runner = Runner(args)
    samples = [s for s in data.load() if not args.conversations or s["sample_id"] in args.conversations]
    for sample in samples:
        print(f"{sample['sample_id']}: ingest", flush=True)
        if not args.skip_ingest:
            runner.ingest(sample)
        print(f"{sample['sample_id']}: questions", flush=True)
        runner.questions(sample)
    s = runner.summary()
    print(json.dumps(s["scores"], indent=1))


if __name__ == "__main__":
    main()
