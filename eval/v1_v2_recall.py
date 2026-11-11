"""v1 vs v2 chunker on the TUNING questions (K, 2026-11-11 §53). No Groq.

  .venv/bin/python eval/v1_v2_recall.py      -> stdout + raw/v1_v2_recall_{stamp}.md

Same method as eval/settings_table.py and eval/cutoffs_by_size.py, so v1 reproduces those tables:
- recall@k of the labelled passage (eval/recall.labelled / found), query = whichever of the raw question and
  the stored rewrite has the higher gate (gate = max cross-encoder score over the k pieces sent, BM25 order;
  for re-rank, over the 20 candidates);
- split into TABLE questions and the rest, so a regression elsewhere shows up. Table question (defined here,
  mechanically): at least one of its checkable must_include facts appears inside a captioned table region
  (relay/ingest.table_regions) on one of its cited pages;
- the 250/3 BM25-order cutoff by K's midpoint rule (fallback: fewest errors, lower on a tie), tuning only, with
  the gap, for v1 (check: must give 0.713) and v2.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from eval.check_questions import parse_pages, resolve_paper  # noqa: E402
from eval.cutoffs_by_size import cutoff, errors_at, facts_of  # noqa: E402
from eval.recall import found, labelled  # noqa: E402
from load.mix import load_pool, load_rewrites, stand_in_query  # noqa: E402
from relay.config import RetrievalSetting  # noqa: E402
from relay.ingest import table_regions  # noqa: E402
from relay.retrieval import Retriever, cross_encoder  # noqa: E402
from relay.textnorm import match_key  # noqa: E402

CANDS = [("BM25 order", 3), ("BM25 order", 6), ("re-rank", 6)]


def table_text_by_page():
    """Text inside captioned table regions, per paper and page."""
    out = {}
    for pid in ("1706.03762v7", "2410.00037v1", "2507.07955v2"):
        doc = pymupdf.open(ROOT / f"papers/{pid}.pdf")
        for pno, ts in table_regions(pid).items():
            ws = doc[pno - 1].get_text("words")
            for t in ts:
                b = t["bbox"]
                txt = " ".join(w[4] for w in ws if w[0] >= b[0] - 2 and w[2] <= b[2] + 2 and w[1] >= b[1] - 25 and w[3] <= b[3] + 2)
                out.setdefault((pid, pno), []).append((t["n"], match_key(txt)))
    return out


def is_table_q(p, ttext):
    """Table question = a must_include fact sits inside a table region on a cited page."""
    facts = facts_of(p)
    papers = [x.strip() for x in p["meta"]["paper"].split(";") if x.strip()]
    pages = [x.strip() for x in p["meta"]["page"].split(";") if x.strip()]
    hits = []
    for ps, pg in zip(papers, pages):
        v = resolve_paper(ps)
        for pno in parse_pages(pg):
            for n, txt in ttext.get((v, pno), []):
                if any(f in txt for f in facts):
                    hits.append(f"{v.split('v')[0][-5:]} T{n}")
    return hits


def main():
    """Recall v1 vs v2 (table and other questions) and the 250/3 cutoff for each."""
    pool = {p["id"]: p for p in load_pool()}
    rw = load_rewrites()
    cross_encoder()
    ttext = table_text_by_page()
    tuning = [p for p in pool.values() if p["set"] == "tuning"]
    lab = [p for p in tuning if p["meta"].get("paper", "").strip() and p["meta"].get("page", "").strip()]
    tq = {p["id"]: is_table_q(p, ttext) for p in lab}
    gate_rows = [(pool[r["id"]], r["search_query"]) for r in rw.values() if r["kind"] == "k" and pool[r["id"]]["set"] == "tuning"]
    L = [f"# v1 vs v2 chunker, tuning questions, 250 words ({dt.datetime.now().isoformat(timespec='minutes')})", "",
         f"Table questions ({sum(bool(v) for v in tq.values())} of {len(lab)} labelled): "
         + ", ".join(f"{k} ({'; '.join(v)})" for k, v in tq.items() if v), ""]
    res, cut = {}, {}
    for ch in ("v1", "v2"):
        ret = Retriever(RetrievalSetting(250, 20, True, chunker=ch))
        idx = {id(c): i for i, c in enumerate(ret.chunks)}
        ret.search("warm-up query about attention heads", k=20)
        cache = {}

        def s20(q):
            """Top-20 search for a query, cached."""
            if q not in cache:
                hits, g20, _ = ret.search(q, k=20)
                cache[q] = (hits, sorted(hits, key=lambda h: -h.bm25), g20)
            return cache[q]
        for name, k in CANDS:
            per = {}
            for p in lab:
                groups = labelled(p, ret.chunks)
                if not groups:
                    continue
                q_rw, is_rw = stand_in_query(p, rw)          # same lookup as eval/settings_table.py
                qs = [p["q"]] + ([q_rw] if is_rw else [])

                def g(q):
                    """Gate score of a query under this setting."""
                    ce, bm, g20 = s20(q)
                    return g20 if name == "re-rank" else max(h.ce for h in bm[:k])
                win = max(qs, key=g)
                ce, bm, _ = s20(win)
                sent = (ce if name == "re-rank" else bm)[:k]
                per[p["id"]] = found(groups, [idx[id(h.chunk)] for h in sent], k)
            res[(ch, name, k)] = per
        rows = []
        for p, q_rw in gate_rows:
            def g3(q):
                """Gate score with the top 3 BM25 pieces."""
                _, bm, _ = s20(q)
                return max(h.ce for h in bm[:3])
            s = max(g3(p["q"]), g3(q_rw) if q_rw else -1e9)
            rows.append({"id": p["id"], "ans": p["ans"], "ge": p["meta"]["gate_expected"].lower(), "type": p["type"], "s": s})
        cut[ch] = rows
    L += ["| setting | chunker | table questions | other questions | all |", "|---|---|---|---|---|"]
    for name, k in CANDS:
        for ch in ("v1", "v2"):
            per = res[(ch, name, k)]
            t = [v for q, v in per.items() if tq[q]]
            o = [v for q, v in per.items() if not tq[q]]
            L.append(f"| 250/{k} {name} | {ch} | {sum(t)}/{len(t)} | {sum(o)}/{len(o)} | {sum(per.values())}/{len(per)} |")
    L += ["", "Questions whose recall changed v1 -> v2 (250/3 BM25 order):"]
    a, b = res[("v1", "BM25 order", 3)], res[("v2", "BM25 order", 3)]
    ch_ = [f"{q} {'found->missed' if a[q] else 'missed->found'}{' (table q)' if tq[q] else ''}" for q in a if a[q] != b.get(q)]
    L.append(", ".join(ch_) or "none")
    L += ["", "## 250/3 BM25-order cutoff, K's midpoint rule, tuning only", "",
          "| chunker | highest refuse | lowest answerable above it | gap | cutoff | rule | errors (answerable refused / false-premise refused / refuse passed) |",
          "|---|---|---|---|---|---|---|"]
    for ch in ("v1", "v2"):
        rows = cut[ch]
        h, lo, c, how = cutoff(rows)
        hid = max((r for r in rows if r["ge"] == "refuse"), key=lambda r: r["s"])["id"]
        loid = min((r for r in rows if r["ans"] and r["s"] > h), key=lambda r: r["s"])["id"] if lo is not None else "-"
        ar, fp, rp = errors_at(rows, c)
        L.append(f"| {ch} | {h:.3f} ({hid}) | {'-' if lo is None else f'{lo:.3f} ({loid})'} | "
                 f"{'none' if lo is None else f'{lo - h:.3f}'} | **{c:.3f}** | {how} | "
                 f"{', '.join(ar) or '-'} / {', '.join(fp) or '-'} / {', '.join(rp) or '-'} |")
    txt = "\n".join(L)
    print(txt)
    out = ROOT / f"raw/v1_v2_recall_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    out.write_text(txt + "\n")
    print(f"\n-> {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
