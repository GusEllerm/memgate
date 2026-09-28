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
