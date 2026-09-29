"""Answer and judge prompts, shared by every memory system so only retrieval varies."""

ANSWER = """You answer questions about a long-running conversation between {speakers}, using only the memories retrieved below. Each memory may start with the date it refers to or was recorded.

Rules:
- Use the memories; if they conflict, prefer the most recent one.
- Resolve relative dates ("last year", "two weeks ago") against the memory's date and answer with an absolute date.
- Answer in a short phrase (at most about 10 words). No explanation.
- If the memories don't contain the answer, give your best guess from them.

Memories:
{memories}

Question: {question}
Answer:"""

JUDGE = """You are grading a question-answering system against a gold answer.
Mark CORRECT if the generated answer refers to the same thing as the gold answer, even if it is worded differently, is longer, or gives a date in another format. For time questions, CORRECT if it names the same date or period. Otherwise mark WRONG.

Question: {question}
Gold answer: {gold}
Generated answer: {answer}

Reply with JSON only: {{"reasoning": "<one sentence>", "label": "CORRECT" or "WRONG"}}"""

# Hindsight's paper-era LoCoMo judge (vectorize-io/hindsight @ fa554b89,
# hindsight-dev/benchmarks/common/benchmark_runner.py, default branch), kept verbatim apart from the
# JSON output line so our label parser reads it. Much more lenient than JUDGE: "as long as it
# touches on the same topic". Used only to compare with published numbers.
JUDGE_LENIENT = """Your task is to label an answer to a question as 'CORRECT' or 'WRONG'. You will be given the following data:
        (1) a question (posed by one user to another user),
        (2) a 'gold' (ground truth) answer,
        (3) a generated answer
    which you will score as CORRECT/WRONG.

    The point of the question is to ask about something one user should know about the other user based on their prior conversations.
    The gold answer will usually be a concise and short answer that includes the referenced topic, for example:
    Question: Do you remember what I got the last time I went to Hawaii?
    Gold answer: A shell necklace
    The generated answer might be much longer, but you should be generous with your grading - as long as it touches on the same topic as the gold answer, it should be counted as CORRECT.

    For time related questions, the gold answer will be a specific date, month, year, etc. The generated answer might be much longer or use relative time references (like "last Tuesday" or "next month"), but you should be generous with your grading - as long as it refers to the same date or time period as the gold answer, it should be counted as CORRECT. Even if the format differs (e.g., "May 7th" vs "7 May"), consider it CORRECT if it's the same date.
    There's an edge case where the actual answer can't be found in the data and in that case the gold answer will say so (e.g. 'You did not mention this information.'); if the generated answer says that it cannot be answered or it doesn't know all the details, it should be counted as CORRECT.

Question: {question}
Gold answer: {gold}
Generated answer: {answer}
First, provide a short (one sentence) explanation of your reasoning. Short reasoning is preferred.
Reply with JSON only: {{"reasoning": "<one sentence>", "label": "CORRECT" or "WRONG"}}"""
