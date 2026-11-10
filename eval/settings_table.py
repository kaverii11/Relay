"""2a (K, 2026-11-11, PENDING her choice of three): candidate retrieval settings on the tuning questions. No Groq.

  .venv/bin/python eval/settings_table.py            # -> raw/settings_table_{stamp}.md (+ stdout)

Grid: piece size 120 / 250 / 500 words  x  pieces fetched k in (2, 3, 4, 6, 8)  x  re-rank yes / no.
Per row, on the tuning questions that have a labelled passage (eval/recall.py labels; eval rows held out):
  recall@k      the labelled passage is among the k pieces sent (cross-paper rows: every cited paper)
  draft tokens  mean estimated draft prompt tokens (relay.pipeline.est_tokens on the real draft prompt)
  rerank ms     p50 cross-encoder time on the critical path (the pass whose pieces are sent)
Gate input is production's max(raw, rewrite) (K §29): the query with the higher gate wins and ITS pieces go
to the drafter.
Definitions (2c):
  re-rank    cross-encoder scores BM25's top-20 (RetrievalSetting.candidates), the best k are sent in
             cross-encoder order; gate = max score over the 20.
  no re-rank BM25's top-k are sent in BM25 order; the cross-encoder scores ONLY those k pieces, for the
             gate (gate = max over the k). That is what relay/retrieval.py does (search(), rerank=False).
Ladder: fewer_chunks rung = max(2, k // 2) pieces of the setting (relay/pipeline._plan_draft); rows that are
a current setting or its rung are labelled.
"""
from __future__ import annotations

import datetime as dt
import statistics as st
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from eval.recall import found, labelled  # noqa: E402
from load.mix import load_pool, load_rewrites, stand_in_query  # noqa: E402
from relay.config import SETTINGS, RetrievalSetting  # noqa: E402
from relay.pipeline import est_tokens  # noqa: E402
from relay.prompts import draft_messages  # noqa: E402
from relay.retrieval import Retriever, cross_encoder  # noqa: E402

WORDS = (120, 250, 500)
KS = (2, 3, 4, 6, 8)


def main():
    rw = load_rewrites()
    cross_encoder()
    rows = [p for p in load_pool() if p["set"] == "tuning" and p["meta"].get("paper", "").strip()
            and p["meta"].get("page", "").strip()]
    labels = {}
    for name, s in SETTINGS.items():
        labels[(s.words, s.k, s.rerank)] = f"current `{name}`"
        labels.setdefault((s.words, max(2, s.k // 2), s.rerank), f"fewer_chunks rung of `{name}`")
    lines = [f"# Candidate retrieval settings (tuning questions, max(raw, rewrite) gate input) "
             f"{dt.datetime.now().isoformat(timespec='minutes')}", "",
             "| words | pieces | k sent | re-rank | recall@k | draft tokens (mean) | rerank ms p50 | note |",
             "|---|---|---|---|---|---|---|---|"]
    for w in WORDS:
        ret = Retriever(RetrievalSetting(w, 20, True))
        chunks = ret.chunks
        idx = {id(c): i for i, c in enumerate(chunks)}
        ret.search("warm-up query about attention heads", k=20)
        per_q = []
        for p in rows:
            groups = labelled(p, chunks)
            if not groups:
                continue
            qs = {"raw": p["q"]}
            q_rw, is_rw = stand_in_query(p, rw)
            if is_rw:
                qs["rewrite"] = q_rw
            d = {}
            for qk, q in qs.items():
                hits, gate, tms = ret.search(q, k=20)          # cross-encoder order, all 20 scored
                d[qk] = {"q": q, "ce": hits, "bm": sorted(hits, key=lambda h: -h.bm25), "gate20": gate,
                         "ce_ms": tms["ce_ms"]}
            per_q.append((p, groups, d))
        n = len(per_q)
        for rr in (True, False):
            for k in KS:
                rec, toks, ms = [], [], []
                for p, groups, d in per_q:
                    def gate(x):
                        return x["gate20"] if rr else max(h.ce for h in x["bm"][:k])
                    win = max(d, key=lambda qk: gate(d[qk]))
                    sent = (d[win]["ce"] if rr else d[win]["bm"])[:k]
                    rec.append(found(groups, [idx[id(h.chunk)] for h in sent], k))
                    toks.append(est_tokens(draft_messages(p["q"], sent)))
                    if rr:
                        ms.append(d[win]["ce_ms"])
                    else:
                        t0 = time.perf_counter()
                        ret._ce_scores(d[win]["q"], [h.chunk for h in sent])
                        ms.append((time.perf_counter() - t0) * 1000)
                lines.append(f"| {w} | {len(chunks)} | {k} | {'yes' if rr else 'no'} | {sum(rec)}/{n} | "
                             f"{st.mean(toks):.0f} | {st.median(ms):.0f} | {labels.get((w, k, rr), '')} |")
    txt = "\n".join(lines)
    print(txt)
    out = ROOT / f"raw/settings_table_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    out.write_text(txt + "\n")
    print(f"\n-> {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
