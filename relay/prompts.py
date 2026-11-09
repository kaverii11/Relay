"""Prompts used by the pipeline. Kept in one place so the probe sends exactly what the pipeline sends."""

PAPERS_BLURB = """The library has exactly three papers:
- 1706.03762v7 "Attention Is All You Need" (the Transformer)
- 2410.00037v1 "Moshi: a speech-text foundation model for real-time dialogue" (Moshi, Mimi codec, Helium)
- 2507.07955v2 "Dynamic Chunking for End-to-End Hierarchical Sequence Modeling" (H-Net, dynamic chunking)"""

UNDERSTAND_SYSTEM = f"""You route questions for an assistant that answers ONLY from a small library of papers.
{PAPERS_BLURB}

Rewrite the question for retrieval. Do not judge whether the papers answer it.
Return ONLY a JSON object, no prose:
{{"papers": ["1706.03762v7", ...],  // which papers look most relevant (a search hint, never a filter)
  "search_query": "...",            // a specific keyword query using the papers' own terms
  "needs_numbers": true|false,      // does the answer hinge on a specific number/table value?
  "cross_paper": true|false}}        // does it need more than one paper?
Do not answer the question."""


def understand_messages(question: str):
    return [{"role": "system", "content": UNDERSTAND_SYSTEM},
            {"role": "user", "content": question}]


DRAFT_SYSTEM = """You answer engineers' questions using ONLY the numbered passages given (from three arXiv papers).
Rules:
- Every claim must be backed by a passage: give its id (e.g. "C2") and a short quote copied WORD FOR WORD from that passage.
- If the passages do not contain the answer, set "not_in_papers": true. Do not guess, and do not use outside knowledge.
- Watch for numbers that belong to OTHER systems or baselines in a table: only report a number for the system asked about.
- If the question states a value (a number, setting or name), compare it with the passages. If they disagree, say so
  and give the value the passages report, with its citation. Do not answer as if the stated value were true.
Return ONLY JSON:
{"not_in_papers": false,
 "answer": "2-4 sentences, with [C#] after each claim",
 "claims": [{"chunk": "C2", "quote": "exact words from passage C2"}]}"""


def draft_messages(question: str, hits, feedback: str | None = None):
    ctx = "\n\n".join(f"[C{i + 1}] {h.chunk.cite()}\n{h.chunk.text}" for i, h in enumerate(hits))
    user = f"Passages:\n{ctx}\n\nQuestion: {question}"
    if feedback:
        user += f"\n\nYour previous answer failed verification: {feedback}\nFix it, or set not_in_papers."
    return [{"role": "system", "content": DRAFT_SYSTEM}, {"role": "user", "content": user}]


CHECK_SYSTEM = """You verify a drafted answer against its cited quotes. For each claim, decide whether the
quote actually supports what the answer says, including whether any number is for the right system,
setting and table row. Return ONLY JSON: {"supported": true|false, "problems": ["short reason", ...]}"""


def check_messages(question: str, answer: str, claims_with_quotes):
    lines = "\n".join(f"- {c['chunk']}: \"{c['quote']}\"" for c in claims_with_quotes)
    return [{"role": "system", "content": CHECK_SYSTEM},
            {"role": "user", "content": f"Question: {question}\n\nAnswer: {answer}\n\nQuotes:\n{lines}"}]
