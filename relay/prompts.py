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
    """Messages for step 1: the 20b rewrite (search query, paper hint, flags)."""
    return [{"role": "system", "content": UNDERSTAND_SYSTEM},
            {"role": "user", "content": question}]


DRAFT_SYSTEM = """You answer engineers' questions using ONLY the numbered passages given (from three arXiv papers).
Rules:
- Every claim must be backed by a passage: give its id (e.g. "C2") and one or more short quotes, each copied WORD FOR
  WORD from that passage. If the evidence is in two sentences, give two quotes; never join sentences with "...".
- If the passages do not contain the answer, set "not_in_papers": true. Do not guess, and do not use outside knowledge.
- Watch for numbers that belong to OTHER systems or baselines in a table: only report a number for the system asked about.
- If the question states a value (a number, setting or name), compare it with the passages. If they disagree, say so
  and give the value the passages report, with its citation. Do not answer as if the stated value were true.
Return ONLY JSON:
{"not_in_papers": false,
 "answer": "2-4 sentences, with [C#] after each claim",
 "claims": [{"chunk": "C2", "quotes": ["exact words from passage C2", "more exact words from C2 if needed"]}]}"""


# v2 (K §61, option (i) for the table prefix, part of change a): K's sentence, added to the v1 rules verbatim.
DRAFT_SYSTEM_V2 = DRAFT_SYSTEM.replace(
    "Return ONLY JSON:",
    "- The bracketed [Table N, repeated: ...] text names the table's columns. Use it to read the rows, but quote only\n"
    "  the paper text that follows it.\nReturn ONLY JSON:")


def draft_messages(question: str, hits, feedback: str | None = None, variant: str = "v1"):
    """Messages for step 4: numbered passages + question (+ the check's feedback on a redraft)."""
    ctx = "\n\n".join(f"[C{i + 1}] {h.chunk.cite()}\n{h.chunk.text}" for i, h in enumerate(hits))
    user = f"Passages:\n{ctx}\n\nQuestion: {question}"
    if feedback:
        user += f"\n\nYour previous answer failed verification: {feedback}\nFix it, or set not_in_papers."
    return [{"role": "system", "content": DRAFT_SYSTEM_V2 if variant == "v2" else DRAFT_SYSTEM},
            {"role": "user", "content": user}]


CHECK_SYSTEM = """You verify a drafted answer against the cited passages. The quotes show where in each passage the
drafter looked; judge each claim against the WHOLE cited passage, not only the quote. A claim is supported when
the passage states it, including that any number is for the right system, setting and table row. A claim is NOT
supported if the passage contradicts it or does not contain it (the question's own wording is not evidence).
Return ONLY JSON: {"supported": true|false, "problems": ["short reason", ...]}"""


# v2 (K §51 b): the same check, plus number provenance. Selected by Policy.check_prompt = "v2"; v1 above is unchanged.
CHECK_SYSTEM_V2 = """You verify a drafted answer against the cited passages. The quotes show where in each passage the
drafter looked; judge each claim against the WHOLE cited passage, not only the quote. A claim is supported when
the passage states it, including that any number is for the right system, setting and table row. A claim is NOT
supported if the passage contradicts it or does not contain it (the question's own wording is not evidence).
For EVERY number in the answer, name where the cited passage shows it: for a table, the table, the row and the
column (use the table's header row, which may be repeated at the start of the passage in [Table N, repeated:
...]); for prose, the sentence. If the passage does not show which row and column (or which sentence) the number
comes from, or shows it under a different row or column than the answer says, the claim is NOT supported.
Return ONLY JSON: {"numbers": [{"value": "...", "where": "Table N, row ..., column ..." or "sentence: ..."}],
"supported": true|false, "problems": ["short reason", ...]}"""


def claim_quotes(c) -> list[str]:
    """A claim's quotes: "quotes": [...] (current drafter) or the older single "quote"."""
    qs = c.get("quotes")
    if qs is None:
        qs = [c.get("quote", "")]
    return [q for q in (qs if isinstance(qs, list) else [qs]) if isinstance(q, str) and q.strip()]


def check_messages(question: str, answer: str, claims, hits, variant: str = "v1"):
    """K (2026-11-10, §37): the checker sees the whole text of every CITED passage, plus the quotes.
    variant "v2" (K §51 b): the number-provenance prompt; the user message is the same."""
    cited = sorted({str(c.get("chunk", "")) for c in claims}, key=lambda s: int(s[1:]) if s[1:].isdigit() else 0)
    passages = "\n\n".join(f"[{cid}] {hits[int(cid[1:]) - 1].chunk.text}" for cid in cited
                           if cid[1:].isdigit() and 1 <= int(cid[1:]) <= len(hits))
    lines = "\n".join(f"- {c.get('chunk')}: " + " | ".join(f"\"{q}\"" for q in claim_quotes(c)) for c in claims)
    return [{"role": "system", "content": CHECK_SYSTEM_V2 if variant == "v2" else CHECK_SYSTEM},
            {"role": "user", "content": f"Question: {question}\n\nAnswer: {answer}\n\nCited passages:\n{passages}\n\n"
                                        f"Quotes:\n{lines}"}]
