"""2b (K, 2026-11-11, PENDING her decision): a gate cutoff PER SETTING by K's midpoint rule (DECISIONS §29, §41),
gate input max(raw, rewrite), on the tuning questions. No Groq.

  .venv/bin/python eval/cutoffs_by_size.py           # -> raw/cutoffs_by_size_{stamp}.md (+ stdout)

Rule (K §41, logged before these tables were computed): every setting gets its own cutoff by the midpoint
rule, including no-re-rank settings, whose gate is the max cross-encoder score over the k pieces SENT (BM25's
top-k), not over the 20 candidates. If a setting has no gap (no answerable score above the highest refuse
score), the cutoff is the one with the fewest errors on the tuning questions, the lower one on a tie.
Errors = answerable refused + false-premise unanswerable refused (= wrong, §6) + refuse-expected passed.
Candidates: re-rank (gate over the 20; independent of k) and no-re-rank with k in (2, 3, 4, 6, 8), per size.
512-token window (K: "flag any size where the 512-token cut hurts"): the cross-encoder's input is 512 tokens;
relay/retrieval.py scores a piece longer than WINDOW_WORDS words in windows of WINDOW_WORDS (+40 words of
overlap) and keeps the max. The cut can hurt only if a labelled fact is split by a window boundary (no window
holds it whole) — counted per size as "facts split", with the question ids.
"""
from __future__ import annotations

import datetime as dt
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from eval.check_questions import MIN_KEY  # noqa: E402
from eval.recall import labelled  # noqa: E402
from load.mix import load_pool, load_rewrites  # noqa: E402
from relay.config import RetrievalSetting  # noqa: E402
from relay.retrieval import WINDOW_WORDS, Retriever, cross_encoder  # noqa: E402
from relay.textnorm import match_key  # noqa: E402

WORDS = (120, 250, 500)
KS = (2, 3, 4, 6, 8)


def facts_of(p):
    """The question's must_include facts as match keys (long enough to be specific)."""
    fs = [match_key(f) for f in p["meta"].get("must_include", "").split(";")
          if f.strip() and not re.match(r"(?i)(not|no)\b", f.strip())]
    return [f for f in fs if len(f) >= MIN_KEY]


def windows(text):
    """A long piece split into cross-encoder windows."""
    w = text.split()
    out = []
    for j in range(0, max(1, len(w)), WINDOW_WORDS):
        out.append(" ".join(w[j:j + WINDOW_WORDS + 40]))
        if j + WINDOW_WORDS >= len(w):
            break
    return out


def errors_at(rows, c):
    """Who a cutoff gets wrong: answerable refused, false-premise refused, should-refuse passed."""
    ar = [r["id"] for r in rows if r["ans"] and r["s"] < c]
    fp = [r["id"] for r in rows if not r["ans"] and r["ge"] == "pass" and "false premise" in r["type"].lower() and r["s"] < c]
    rp = [r["id"] for r in rows if r["ge"] == "refuse" and r["s"] >= c]
    return ar, fp, rp


def cutoff(rows):
    """K's midpoint rule; fallback (§41): fewest errors, lower on a tie. Returns (h, lo, c, how)."""
    h = max(r["s"] for r in rows if r["ge"] == "refuse")
    above = [r["s"] for r in rows if r["ans"] and r["s"] > h]
    if above:
        lo = min(above)
        return h, lo, (h + lo) / 2, "midpoint"
    xs = sorted({r["s"] for r in rows})
    cands = [xs[0] - 1] + [(a + b) / 2 for a, b in zip(xs, xs[1:])] + [xs[-1] + 1]
    best = min(cands, key=lambda c: (sum(len(x) for x in errors_at(rows, c)), c))
    return h, None, best, "fewest errors (no gap)"


def main():
    """Cutoff per piece size and setting by K's midpoint rule, tuning questions only."""
    pool = {p["id"]: p for p in load_pool()}
    rw = load_rewrites()
    cross_encoder()
    recs = [r for r in rw.values() if r["kind"] == "k" and pool[r["id"]]["set"] == "tuning"]
    lab_rows = [p for p in pool.values() if p["set"] == "tuning" and p["meta"].get("paper", "").strip()
                and p["meta"].get("page", "").strip()]
    lines = [f"# Cutoff per setting, K's midpoint rule (fallback: fewest errors) on max(raw, rewrite), tuning questions "
             f"{dt.datetime.now().isoformat(timespec='minutes')}", "",
             f"Cross-encoder window: {WINDOW_WORDS} words (+40 overlap), max over windows.", "",
             "| words | re-rank | k sent | highest refuse | lowest answerable above | gap | **cutoff** | rule | "
             "answerable refused | false-premise refused | refuse passed | errors |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    per_size, split_lines = {}, []
    for w in WORDS:
        ret = Retriever(RetrievalSetting(w, 20, True))
        chunks = ret.chunks
        ret.search("warm-up query about attention heads", k=20)
        base = []
        for r in recs:
            p = pool[r["id"]]
            per_q = {}
            for qk, q in (("raw", p["q"]), ("rewrite", r["search_query"])):
                hits, gate20, _ = ret.search(q, k=20)
                per_q[qk] = {"gate20": gate20, "bm": sorted(hits, key=lambda h: -h.bm25)}
            base.append((p, per_q))
        cands = [("yes", None)] + [("no", k) for k in KS]
        for rr, k in cands:
            rows = []
            for p, per_q in base:
                def g(x):
                    """Gate score of one question under this setting."""
                    return x["gate20"] if rr == "yes" else max(h.ce for h in x["bm"][:k])
                s = max(g(per_q["raw"]), g(per_q["rewrite"]))
                rows.append({"id": p["id"], "ans": p["ans"], "ge": p["meta"]["gate_expected"].lower(), "type": p["type"], "s": s})
            h, lo, c, how = cutoff(rows)
            hid = max((r for r in rows if r["ge"] == "refuse"), key=lambda r: r["s"])["id"]
            loid = min((r for r in rows if r["ans"] and r["s"] > h), key=lambda r: r["s"])["id"] if lo is not None else "-"
            ar, fp, rp = errors_at(rows, c)
            lines.append(f"| {w} | {rr} | {k if k else '(20 scored)'} | {h:.3f} ({hid}) | "
                         f"{'-' if lo is None else f'{lo:.3f} ({loid})'} | {'none' if lo is None else f'{lo - h:.3f}'} | "
                         f"**{c:.3f}** | {how} | {len(ar)}: {', '.join(ar) or '-'} | {len(fp)}: {', '.join(fp) or '-'} | "
                         f"{len(rp)}: {', '.join(rp) or '-'} | {len(ar) + len(fp) + len(rp)} |")
            if rr == "yes":
                per_size[w] = {r["id"]: r for r in rows}
        n_long = sum(len(ch.text.split()) > WINDOW_WORDS for ch in chunks)
        split = []
        for p in lab_rows:
            groups = labelled(p, chunks)
            facts = facts_of(p)
            if not groups or not facts:
                continue
            for gset in groups:
                for i in gset:
                    t = chunks[i].text
                    for f in facts:
                        if f in match_key(t) and not any(f in match_key(win) for win in windows(t)):
                            split.append(p["id"])
        split = sorted(set(split), key=lambda s: int(s[1:]))
        split_lines.append(f"| {w} | {len(chunks)} | {n_long} | {len(split)}: {', '.join(split) or '-'}"
                           f"{'  **HURTS**' if split else ''} |")
    lines += ["", "512-token window check per piece size:", "",
              "| words | pieces | pieces longer than one window | labelled facts split by a window boundary |",
              "|---|---|---|---|"] + split_lines
    lines += ["", "Per question, re-rank gate (max over 20) by size:", "",
              "| id | answerable | gate_expected | " + " | ".join(f"w{w}" for w in WORDS) + " |",
              "|---|---|---|" + "---|" * len(WORDS)]
    for r in sorted(per_size[250].values(), key=lambda r: r["s"]):
        lines.append(f"| {r['id']} | {'yes' if r['ans'] else 'no'} | {r['ge']} | "
                     + " | ".join(f"{per_size[w][r['id']]['s']:.2f}" for w in WORDS) + " |")
    txt = "\n".join(lines)
    print(txt)
    out = ROOT / f"raw/cutoffs_by_size_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    out.write_text(txt + "\n")
    print(f"\n-> {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
