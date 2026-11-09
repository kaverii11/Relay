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
