"""Text normalisation for PDF-extracted text.

Two different jobs:
1. dehyphenate(): fix line-break hyphens in the stored chunk text. A word split
   across lines ("transduc-\\ntion") and a real hyphenated word that happens to
   break at a line end ("position-\\nwise") look identical. We decide using the
   papers' own vocabulary: if the joined form occurs elsewhere in the corpus, join;
   otherwise keep the hyphen.
2. match_key(): a lossy canonical form used ONLY for checking that a quoted span
   appears in a chunk. NFKC (ligatures, odd unicode), casefold, then drop everything
   that isn't a letter or digit, so hyphen/whitespace/line-break differences can't
   cause false "quote not found" failures (each false failure costs a redraft call).
"""
from __future__ import annotations

import re
import unicodedata

_LINEBREAK_HYPHEN = re.compile(r"(\w+)-\n(\w+)")


def dehyphenate(text: str, vocab: set[str]) -> str:
    def fix(m):
        a, b = m.group(1), m.group(2)
        return a + b if (a + b).lower() in vocab else f"{a}-{b}"
    return _LINEBREAK_HYPHEN.sub(fix, text)


def corpus_vocab(texts) -> set[str]:
    """Words that appear unbroken (not at a line-break hyphen) anywhere in the corpus."""
    vocab = set()
    for t in texts:
        clean = _LINEBREAK_HYPHEN.sub(" ", t)
        vocab.update(w.lower() for w in re.findall(r"\w+", clean))
    return vocab


def match_key(s: str) -> str:
    s = unicodedata.normalize("NFKC", s).casefold()
    return re.sub(r"[\W_]+", "", s)


def quote_in(quote: str, passage: str) -> bool:
    q = match_key(quote)
    return len(q) >= 12 and q in match_key(passage)
