"""The harder-question rules (no LLM): what a paraphrase or an indirect question may and may not contain."""

import pytest

pytest.importorskip("memgate")

from smbench.selective.questions import content_words, question_for, why_invalid  # noqa: E402
from smbench.selective.world import Fact, World  # noqa: E402

KILN = Fact("f1", "the combination for the kiln", "EMBER-4471")


def test_content_words_drop_stopwords():
    assert content_words("the name chosen for the new research project") == ["name", "research", "project"]
    assert content_words(KILN.topic) == ["combination", "kiln"]


@pytest.mark.parametrize("style, question, ok", [
    ("paraphrase", "What is the access code for the pottery oven?", True),
    ("paraphrase", "What is the combination for the kiln?", False),            # the topic phrase verbatim
    ("paraphrase", "Is it EMBER-4471?", False),                                # the code
    ("paraphrase", "Is it ember 1234?", False),                                # the code's word
    ("paraphrase", "What is the code", False),                                 # not a question
    ("indirect", "What was the code Bo gave for the pottery oven this morning?", True),
    ("indirect", "What is the kiln's code?", False),                           # a banned word
    ("indirect", "Which combinations did we agree on?", False),               # a variant of a banned word
    ("indirect", "What did we settle on for firing the pots?", True),
])
def test_question_rules(style, question, ok):
    assert (why_invalid(style, question, KILN, KILN.topic) is None) is ok


def test_question_for_styles():
    f = Fact("f1", "the code for the kiln", "EMBER-4471", questions={"indirect": "What opens the pottery oven?"})
    w = World(1, ["ada1"], ["lab1"], {"f1": f}, [])
    assert question_for(w, "f1", "direct") == "What is the code for the kiln?"
    assert question_for(w, "f1", "indirect") == "What opens the pottery oven?"
    with pytest.raises(KeyError):
        question_for(w, "f1", "paraphrase")
    assert World.from_json(w.to_json()).facts["f1"].questions == f.questions      # round-trips through the dataset
