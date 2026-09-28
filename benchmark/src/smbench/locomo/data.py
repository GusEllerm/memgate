"""Load LoCoMo (snap-research/locomo, CC BY-NC 4.0). The file is downloaded by scripts/get_locomo.sh."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from smbench.adapters import Session, Turn

DATA = Path("data/locomo/locomo10.json")
SHA256 = "79fa87e90f04081343b8c8debecb80a9a6842b76a7aa537dc9fdf651ea698ff4"

# Category numbering as used by the Mem0 LoCoMo evaluation; 5 (adversarial) is excluded by convention.
CATEGORIES = {1: "multi-hop", 2: "temporal", 3: "open-domain", 4: "single-hop", 5: "adversarial"}


@dataclass
class Question:
    conversation_id: str
    index: int
    question: str
    answer: str
    category: int
    evidence: list[str]


def _when(text: str) -> datetime:
    return datetime.strptime(text.strip(), "%I:%M %p on %d %B, %Y")


def _turn_text(t: dict) -> str:
    text = t["text"]
    if t.get("blip_caption"):
        text += f" [shares an image: {t['blip_caption']}]"
    return text


def load(path: Path = DATA) -> list[dict]:
    return json.loads(path.read_text())


def sessions(sample: dict) -> list[Session]:
    conv = sample["conversation"]
    speakers = (conv["speaker_a"], conv["speaker_b"])
    keys = sorted((k for k in conv if k.startswith("session_") and not k.endswith("date_time")),
                  key=lambda k: int(k.split("_")[1]))
    out = []
    for k in keys:
        idx = int(k.split("_")[1])
        when_text = conv[f"{k}_date_time"]
        turns = [Turn(t["speaker"], _turn_text(t), t["dia_id"]) for t in conv[k]]
        out.append(Session(sample["sample_id"], idx, _when(when_text), when_text, speakers, turns))
    return out


def questions(sample: dict, include_adversarial: bool = False) -> list[Question]:
    out = []
    for i, q in enumerate(sample["qa"]):
        if q["category"] == 5 and not include_adversarial:
            continue
        answer = q.get("answer", q.get("adversarial_answer", ""))
        out.append(Question(sample["sample_id"], i, q["question"], str(answer), q["category"], q.get("evidence", [])))
    return out
