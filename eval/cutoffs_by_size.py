"""2b (K, 2026-11-11, PENDING her decision): a gate cutoff per piece size by K's midpoint rule (DECISIONS §29),
gate input max(raw, rewrite), on the tuning questions. No Groq.

  .venv/bin/python eval/cutoffs_by_size.py           # -> raw/cutoffs_by_size_{stamp}.md (+ stdout)

Gate here = the re-rank gate (max cross-encoder score over BM25's top-20), which does not depend on k.
The no-re-rank gate is the max over BM25's top-k only, so it is lower or equal; see eval/settings_table.py.
512-token window (K: "flag any size where the 512-token cut hurts"): the cross-encoder's input is 512 tokens;
relay/retrieval.py scores a piece longer than WINDOW_WORDS words in windows of WINDOW_WORDS (+40 words of
overlap) and keeps the max. The cut can hurt only if a labelled fact is split by a window boundary (then no
window contains it whole) — counted per size as "facts split".
"""
from __future__ import annotations

import datetime as dt
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from eval.check_questions import MIN_KEY  # noqa: E402
from eval.gate_inputs import rule  # noqa: E402
from eval.recall import labelled  # noqa: E402
from load.mix import load_pool, load_rewrites  # noqa: E402
from relay.config import RetrievalSetting  # noqa: E402
from relay.retrieval import WINDOW_WORDS, Retriever, cross_encoder  # noqa: E402
from relay.textnorm import match_key  # noqa: E402

WORDS = (120, 250, 500)


def facts_of(p):
    fs = [match_key(f) for f in p["meta"].get("must_include", "").split(";")
          if f.strip() and not re.match(r"(?i)(not|no)\b", f.strip())]
    return [f for f in fs if len(f) >= MIN_KEY]


def windows(text):
    w = text.split()
    out = []
    for j in range(0, max(1, len(w)), WINDOW_WORDS):
        out.append(" ".join(w[j:j + WINDOW_WORDS + 40]))
        if j + WINDOW_WORDS >= len(w):
            break
    return out


def main():
    pool = {p["id"]: p for p in load_pool()}
    rw = load_rewrites()
    cross_encoder()
    recs = [r for r in rw.values() if r["kind"] == "k" and pool[r["id"]]["set"] == "tuning"]
    lab_rows = [p for p in pool.values() if p["set"] == "tuning" and p["meta"].get("paper", "").strip()
                and p["meta"].get("page", "").strip()]
    lines = [f"# Cutoff per piece size, K's midpoint rule on max(raw, rewrite), tuning questions "
             f"{dt.datetime.now().isoformat(timespec='minutes')}", "",
             f"Window: {WINDOW_WORDS} words (+40 overlap), max over windows.", "",
             "| words | pieces | pieces > 1 window | highest refuse | lowest answerable above | gap | **cutoff** | "
             "answerable refused | unanswerable-pass refused | refuse passed | facts split by a window boundary |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    detail = []
    for w in WORDS:
        ret = Retriever(RetrievalSetting(w, 6, True))
        chunks = ret.chunks
        ret.search("warm-up query about attention heads")
        rows = []
        for r in recs:
            p = pool[r["id"]]
            raw, rr = ret.search(p["q"])[1], ret.search(r["search_query"])[1]
            rows.append({"id": p["id"], "ans": p["ans"], "ge": p["meta"]["gate_expected"].lower(),
                         "type": p["type"], "max": max(raw, rr), "raw": raw, "rewrite": rr})
        h, lo, c = rule(rows, "max")
        A = [r for r in rows if r["ans"]]
        NR = [r for r in rows if not r["ans"] and r["ge"] == "pass"]
        RF = [r for r in rows if r["ge"] == "refuse"]
        hid = max(RF, key=lambda r: r["max"])["id"]
        loid = min((r for r in A if r["max"] > h), key=lambda r: r["max"])["id"]
        ar = [r["id"] for r in sorted(A, key=lambda r: r["max"]) if r["max"] < c]
        nr = [r["id"] for r in sorted(NR, key=lambda r: r["max"]) if r["max"] < c]
        rp = [r["id"] for r in RF if r["max"] >= c]
        n_long = sum(len(ch.text.split()) > WINDOW_WORDS for ch in chunks)
        split = []
        for p in lab_rows:
            groups = labelled(p, chunks)
            facts = facts_of(p)
            if not groups or not facts:
                continue
            for g in groups:
                for i in g:
                    t = chunks[i].text
                    for f in facts:
                        if f in match_key(t) and not any(f in match_key(win) for win in windows(t)):
                            split.append(p["id"])
        split = sorted(set(split), key=lambda s: int(s[1:]))
        lines.append(f"| {w} | {len(chunks)} | {n_long} | {h:.3f} ({hid}) | {lo:.3f} ({loid}) | {lo - h:.3f} | "
                     f"**{c:.3f}** | {len(ar)}/{len(A)}: {', '.join(ar) or '-'} | {len(nr)}/{len(NR)}: "
                     f"{', '.join(nr) or '-'} | {len(rp)}/{len(RF)} | {len(split)}: {', '.join(split) or '-'}"
                     f"{'  **HURTS**' if split else ''} |")
        detail.append((w, sorted(rows, key=lambda r: r["max"])))
    lines += ["", "Per question (max score) by size:", "",
              "| id | answerable | gate_expected | " + " | ".join(f"w{w}" for w in WORDS) + " |",
              "|---|---|---|" + "---|" * len(WORDS)]
    by_id = {w: {r["id"]: r for r in rs} for w, rs in detail}
    for r in detail[1][1]:
        lines.append(f"| {r['id']} | {'yes' if r['ans'] else 'no'} | {r['ge']} | "
                     + " | ".join(f"{by_id[w][r['id']]['max']:.2f}" for w in WORDS) + " |")
    txt = "\n".join(lines)
    print(txt)
    out = ROOT / f"raw/cutoffs_by_size_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    out.write_text(txt + "\n")
    print(f"\n-> {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
