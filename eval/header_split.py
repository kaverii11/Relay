"""For each question about a table: under v1 chunking, is the table's header row in a different piece from the
row that holds the answer? (K, 2026-11-11 §59 item 1.) No Groq.

  .venv/bin/python eval/header_split.py eval/k_questions_new.csv            # the new questions (Q61-Q70)
  .venv/bin/python eval/header_split.py eval/k_questions.csv --ids Q9,Q15  # check on known cases

Per question: the captioned table on a cited page whose region holds a must_include fact (relay/ingest
.table_regions); the pieces that hold part of that table (v1 windows = v2 windows; v2's `tables` field says
which); among them, ANSWER pieces = those whose text holds the fact, HEADER pieces = those holding at least 60 %
of the header's word tokens. "Split" = no piece is both. Prints piece ids.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from eval.check_questions import parse_pages, resolve_paper  # noqa: E402
from eval.cutoffs_by_size import facts_of  # noqa: E402
from load.mix import load_pool  # noqa: E402
from relay.ingest import load, table_regions  # noqa: E402
from relay.textnorm import match_key  # noqa: E402


NUMTOK = re.compile(r"^[-+]?\d+(?:[.,]\d+)?%?$")


def facts(p):
    """must_include facts: numbers kept as exact tokens (any length, e.g. "42.2"); words via facts_of (>= MIN_KEY)."""
    raw = [x.strip() for x in p["meta"].get("must_include", "").split(";") if x.strip()]
    nums = [("num", x.rstrip("%")) for x in raw if NUMTOK.match(x)]
    return nums + [("key", f) for f in facts_of(p)]


def has(kind, f, tokens, key):
    return f in tokens if kind == "num" else f in key


def toks(text):
    return {t.strip("()[],;:%") for t in re.split(r"[\s±]+", text) if t}


def main():
    path = Path(sys.argv[1])
    ids = set(sys.argv[sys.argv.index("--ids") + 1].split(",")) if "--ids" in sys.argv else None
    qs = [p for p in load_pool(path) if ids is None or p["id"] in ids]
    v2 = load(ROOT / "data/chunks_w250_v2.jsonl")          # same windows and ids as v1; `tables` marks table pieces
    regs, docs = {}, {}
    print("| question | table | answer fact | pieces holding the table | answer piece(s) | header piece(s) | header split from answer row? |")
    print("|---|---|---|---|---|---|---|")
    for p in qs:
        fs = facts(p)
        papers = [x.strip() for x in p["meta"].get("paper", "").split(";") if x.strip()]
        pages = [x.strip() for x in p["meta"].get("page", "").split(";") if x.strip()]
        hit = None
        for ps, pg in zip(papers, pages):
            v = resolve_paper(ps)
            regs.setdefault(v, table_regions(v))
            docs.setdefault(v, pymupdf.open(ROOT / f"papers/{v}.pdf"))
            for pno in parse_pages(pg):
                ws = docs[v][pno - 1].get_text("words")
                for t in regs[v].get(pno, []):
                    b = t["bbox"]
                    raw = " ".join(w[4] for w in ws if w[0] >= b[0] - 2 and w[2] <= b[2] + 2
                                   and w[1] >= b[1] - 25 and w[3] <= b[3] + 2)
                    f = next(((k, x) for k, x in fs if has(k, x, toks(raw), match_key(raw))), None)
                    if f:
                        hit = (v, t, f)
                        break
                if hit:
                    break
            if hit:
                break
        if not hit:
            print(f"| {p['id']} | none found (no must_include fact inside a captioned table on a cited page) | | | | | n/a |")
            continue
        v, t, f = hit
        pieces = [c for c in v2 if c.paper == v and c.tables and t["n"] in c.tables]
        htoks = [match_key(x) for x in re.findall(r"[A-Za-z][\w.-]*", t["header"])]
        htoks = [x for x in htoks if len(x) >= 2]
        ans = [c for c in pieces if has(f[0], f[1], toks(c.body), match_key(c.body))]
        f = f[1]
        head = [c for c in pieces if htoks and sum(x in match_key(c.body) for x in htoks) / len(htoks) >= 0.6]
        idn = lambda cs: ", ".join(c.id.split(":")[1] for c in cs) or "-"  # noqa: E731
        split = "n/a (answer not found in a table piece)" if not ans else ("**yes**" if not set(map(id, ans)) & set(map(id, head)) else "no")
        print(f"| {p['id']} | {v} Table {t['n']} | {f} | {idn(pieces)} | {idn(ans)} | {idn(head)} | {split} |")


if __name__ == "__main__":
    main()
