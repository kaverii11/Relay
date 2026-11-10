"""Free recall test (K, 2026-11-10): BM25 vs embeddings vs hybrid on the tuning questions' labelled
passages. No Groq calls.

  .venv/bin/python eval/recall.py                # w250 pieces (the gate's setting), rewritten + raw queries
  .venv/bin/python eval/recall.py --words 120

Labelled passage = a piece from the cited paper whose pages overlap the cited page(s) AND that contains
at least one checkable must_include fact (same normalisation and same "not ..." filter as
eval/check_questions.py). If no fact is long enough to check, any piece overlapping the cited page counts.
A cross-paper row counts as found only when EVERY cited paper has a labelled piece in the top N.
Rows: tuning questions with paper + page (answerable, and unanswerable-but-pass rows that point to the
nearest passage). Eval questions are held out.

Methods (ranking all pieces of the setting):
  bm25    BM25Okapi on \\w+ tokens (production's first stage)
  embed   BAAI/bge-small-en-v1.5 cosine (query instruction prefix, normalised); not used in production
  hybrid  reciprocal-rank fusion of bm25 and embed, k=60
  prod    production: BM25 top-20 re-ranked by the cross-encoder; recall@k only (it cannot see past BM25's 20)
Reports recall@6 (pieces sent to the drafter) and recall@20 (the re-ranker's candidate pool).
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from eval.check_questions import MIN_KEY, parse_pages, resolve_paper  # noqa: E402
from load.mix import load_pool, load_rewrites  # noqa: E402
from relay.config import RetrievalSetting  # noqa: E402
from relay.retrieval import Retriever, _tok, cross_encoder  # noqa: E402
from relay.textnorm import match_key  # noqa: E402

EMBED = "BAAI/bge-small-en-v1.5"
QPREFIX = "Represent this sentence for searching relevant passages: "
RRF_K = 60


def labelled(row, chunks):
    papers = [x.strip() for x in row["meta"]["paper"].split(";") if x.strip()]
    pages = [x.strip() for x in row["meta"]["page"].split(";") if x.strip()]
    facts = [match_key(f) for f in row["meta"].get("must_include", "").split(";")
             if f.strip() and not re.match(r"(?i)(not|no)\b", f.strip())]
    facts = [f for f in facts if len(f) >= MIN_KEY]
    groups = []
    for ps, pg in zip(papers, pages):
        v, pr = resolve_paper(ps), parse_pages(pg)
        if not v or not pr:
            return None
        over = [i for i, c in enumerate(chunks) if c.paper == v and c.page_start <= max(pr) and c.page_end >= min(pr)]
        with_fact = [i for i in over if any(f in match_key(chunks[i].text) for f in facts)]
        groups.append(set(with_fact or over))
    return groups


def found(groups, ranked, n):
    top = set(ranked[:n])
    return all(g & top for g in groups)


def first_rank(groups, ranked):
    """1-based rank at which the last cited paper's labelled piece first appears (None if never)."""
    pos = {i: r for r, i in enumerate(ranked, 1)}
    rs = [min((pos[i] for i in g if i in pos), default=None) for g in groups]
    return None if None in rs else max(rs)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--words", type=int, default=250)
    a = ap.parse_args()
    s = RetrievalSetting(a.words, 6, True)
    ret = Retriever(s)
    chunks = ret.chunks
    from sentence_transformers import SentenceTransformer
    emb = SentenceTransformer(EMBED)
    C = emb.encode([c.text for c in chunks], normalize_embeddings=True, batch_size=32, show_progress_bar=False)
    cross_encoder()
    rw = load_rewrites()

    rows = [p for p in load_pool() if p["set"] == "tuning" and p["meta"].get("paper", "").strip()
            and p["meta"].get("page", "").strip()]
    res = {q: {m: [] for m in ("bm25", "embed", "hybrid", "prod")} for q in ("rewrite", "raw")}
    detail = []
    for p in rows:
        groups = labelled(p, chunks)
        if not groups:
            continue
        rec = rw.get(match_key(p["q"]))
        for qk, q in (("rewrite", rec["search_query"] if rec else p["q"]), ("raw", p["q"])):
            bm = ret.bm.get_scores(_tok(q))
            r_bm = list(np.argsort(-bm))
            e = C @ emb.encode([QPREFIX + q], normalize_embeddings=True)[0]
            r_em = list(np.argsort(-e))
            rrf = np.zeros(len(chunks))
            for ranked in (r_bm, r_em):
                for r, i in enumerate(ranked, 1):
                    rrf[i] += 1 / (RRF_K + r)
            r_hy = list(np.argsort(-rrf))
            hits, _, _ = ret.search(q, k=6)
            ids = {id(c): i for i, c in enumerate(chunks)}
            r_pr = [ids[id(h.chunk)] for h in hits]
            for m, ranked in (("bm25", r_bm), ("embed", r_em), ("hybrid", r_hy)):
                res[qk][m].append((found(groups, ranked, 6), found(groups, ranked, 20)))
            res[qk]["prod"].append((found(groups, r_pr, 6), None))
            if qk == "rewrite":
                detail.append((p["id"], len(groups), first_rank(groups, r_bm), first_rank(groups, r_em),
                               first_rank(groups, r_hy), found(groups, r_pr, 6), q))

    n = len(detail)
    print(f"Recall on {n} tuning questions with a labelled passage; pieces w{a.words} ({len(chunks)} pieces); "
          f"embeddings {EMBED}\n")
    print("| query | method | recall@6 | recall@20 |\n|---|---|---|---|")
    for qk in ("rewrite", "raw"):
        for m in ("bm25", "embed", "hybrid", "prod"):
            v = res[qk][m]
            r6 = sum(x[0] for x in v)
            r20 = "-" if m == "prod" else f"{sum(x[1] for x in v)}/{len(v)}"
            label = "prod (BM25 top-20 -> cross-encoder top-6)" if m == "prod" else m
            print(f"| {qk} | {label} | {r6}/{len(v)} | {r20} |")
    print("\nPer question, rewritten query: rank of the labelled piece (cross-paper: rank at which the LAST paper appears)")
    print("| id | papers | bm25 rank | embed rank | hybrid rank | in prod top-6 | query |\n|---|---|---|---|---|---|---|")
    for d in sorted(detail, key=lambda d: (d[2] or 9999)):
        print(f"| {d[0]} | {d[1]} | {d[2]} | {d[3]} | {d[4]} | {'yes' if d[5] else 'NO'} | {d[6]} |")


if __name__ == "__main__":
    main()
