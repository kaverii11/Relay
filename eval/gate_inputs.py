"""Gate input comparison (K, 2026-11-10): raw only, rewrite only, max(raw, rewrite). No Groq calls.

  .venv/bin/python eval/gate_inputs.py

Tuning questions only (eval held out); the 5 wording probes are shown separately as an out-of-sample check.
For each input, K's cutoff rule (DECISIONS §29): midpoint of the gap between the highest `refuse` score
and the lowest answerable (answerable=yes) score above it. At that midpoint it reports:
  - answerable refused                         (graded: refused_wrongly)
  - unanswerable-but-pass refused, by type     (false premise -> wrong, §6; not reported / comparison not made
                                                -> refused_correctly)
  - refuse questions passed                    (0 by construction on tuning; each would cost a 120b draft)
"max" runs retrieval twice in production (two BM25 + cross-encoder passes, no extra Groq call).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from load.mix import load_pool, load_rewrites  # noqa: E402
from relay.config import SETTINGS  # noqa: E402
from relay.retrieval import Retriever, cross_encoder  # noqa: E402
from relay.textnorm import match_key  # noqa: E402

INPUTS = ("raw", "rewrite", "max")


def rule(rows, inp):
    """K's rule: highest refuse score h; lowest answerable score above h; midpoint."""
    h = max(r[inp] for r in rows if r["ge"] == "refuse")
    above = [r[inp] for r in rows if r["ans"] and r[inp] > h]
    lo = min(above) if above else None
    return h, lo, (h + lo) / 2 if lo is not None else None


def main():
    pool = {p["id"]: p for p in load_pool()}
    rw = load_rewrites()
    ret = Retriever(SETTINGS["medium_rerank"])
    cross_encoder()
    ret.search("warm-up query about attention heads")
    g = lambda q: ret.search(q)[1]  # noqa: E731

    rows, probes = [], []
    for rec in rw.values():
        if rec["kind"] == "k":
            p = pool[rec["id"]]
            if p["set"] != "tuning":
                continue
            raw, r_ = g(p["q"]), g(rec["search_query"])
            rows.append({"id": p["id"], "ans": p["ans"], "ge": p["meta"]["gate_expected"].lower(),
                         "type": p["type"], "raw": raw, "rewrite": r_, "max": max(raw, r_)})
        elif rec["kind"] == "wording_probe":
            par = pool[rec["parent_id"]]
            raw, r_ = g(rec["q"]), g(rec["search_query"])
            probes.append({"id": rec["id"], "ans": par["ans"], "ge": par["meta"]["gate_expected"].lower(),
                           "raw": raw, "rewrite": r_, "max": max(raw, r_)})

    A = [r for r in rows if r["ans"]]
    NR = [r for r in rows if not r["ans"] and r["ge"] == "pass"]
    RF = [r for r in rows if r["ge"] == "refuse"]
    print(f"Tuning: answerable n={len(A)}, unanswerable-but-pass n={len(NR)}, refuse n={len(RF)}; "
          f"setting {SETTINGS['medium_rerank'].name}\n")
    print("| input | highest refuse | lowest answerable above it | gap | K-rule cutoff | answerable refused "
          "| unanswerable-pass refused (types) | of which false premise (= wrong) | refuse passed "
          "| graded errors (answerable + false premise refused) | probes on the wrong side |")
    print("|---|---|---|---|---|---|---|---|---|---|---|")
    for inp in INPUTS:
        h, lo, c = rule(rows, inp)
        hid = max(RF, key=lambda r: r[inp])["id"]
        loid = min((r for r in A if r[inp] > h), key=lambda r: r[inp])["id"]
        ar = sorted((r for r in A if r[inp] < c), key=lambda r: r[inp])
        nr = sorted((r for r in NR if r[inp] < c), key=lambda r: r[inp])
        fp = [r for r in nr if "false premise" in r["type"].lower()]
        rp = [r for r in RF if r[inp] >= c]
        wp = [p["id"] for p in probes if (p[inp] >= c) != (p["ge"] == "pass")]
        print(f"| {inp} | {h:.3f} ({hid}) | {lo:.3f} ({loid}) | {lo - h:.3f} | **{c:.3f}** "
              f"| {len(ar)}/{len(A)}: {', '.join(r['id'] for r in ar) or '-'} "
              f"| {len(nr)}/{len(NR)}: {', '.join(r['id'] + ' (' + r['type'].replace('Unanswerable ', '') + ')' for r in nr) or '-'} "
              f"| {len(fp)} | {len(rp)}/{len(RF)} | {len(ar) + len(fp)} | {', '.join(wp) or 'none'} |")

    print("\nPer question (tuning), sorted by rewrite score")
    print("| id | answerable | gate_expected | type | raw | rewrite | max |\n|---|---|---|---|---|---|---|")
    for r in sorted(rows, key=lambda r: r["rewrite"]):
        print(f"| {r['id']} | {'yes' if r['ans'] else 'no'} | {r['ge']} | {r['type']} | {r['raw']:.3f} | {r['rewrite']:.3f} | {r['max']:.3f} |")
    print("\nWording probes (assistant-written; not tuning)")
    print("| id | gate_expected | raw | rewrite | max |\n|---|---|---|---|---|")
    for p in probes:
        print(f"| {p['id']} | {p['ge']} | {p['raw']:.3f} | {p['rewrite']:.3f} | {p['max']:.3f} |")
    missing = [p["id"] for p in pool.values() if p["set"] == "tuning" and match_key(p["q"]) not in rw]
    if missing:
        print(f"\nno stored rewrite for {missing}")


if __name__ == "__main__":
    main()
