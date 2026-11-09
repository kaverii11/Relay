"""Gate scores, raw question vs real 20b rewrite (K §24). No Groq calls.

  .venv/bin/python eval/gate_report.py                 # tuning questions + wording probes
  .venv/bin/python eval/gate_report.py --include-eval  # also K's eval questions (only once the cutoff is fixed)

The eval set is HELD OUT by default, so the cutoff is chosen from tuning questions only.
Gate = max cross-encoder score over the pieces sent (relay.retrieval), setting medium_rerank.
The sweep lists every observed tuning score as a possible cutoff, with what it would do;
it does not pick one (K picks).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from load.mix import load_pool, load_rewrites  # noqa: E402
from relay.config import SETTINGS  # noqa: E402
from relay.retrieval import Retriever, cross_encoder  # noqa: E402
from relay.textnorm import match_key  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--include-eval", action="store_true")
    ap.add_argument("--setting", default="medium_rerank")
    a = ap.parse_args()
    rw = load_rewrites()
    if not rw:
        sys.exit("no eval/rewrites_20b.json yet: run eval/rewrites.py (--plan first)")
    pool = {p["id"]: p for p in load_pool()}
    ret = Retriever(SETTINGS[a.setting])
    cross_encoder()
    ret.search("warm-up query about attention heads")
    g = lambda q: ret.search(q)[1]  # noqa: E731

    rows = []
    for rec in rw.values():
        if rec["kind"] == "k" and rec["set"] == "eval" and not a.include_eval:
            continue
        rows.append({**rec, "raw": g(rec["q"]), "rw": g(rec["search_query"])})
    missing = [p for p in pool.values() if match_key(p["q"]) not in rw
               and (p["set"] != "eval" or a.include_eval)]

    print(f"Gate scores ({SETTINGS[a.setting].name}); eval set {'INCLUDED' if a.include_eval else 'held out'}")
    print("| id | set | answerable | raw score | rewritten score | change | question -> rewrite |")
    print("|---|---|---|---|---|---|---|")
    for r in sorted(rows, key=lambda r: (r["kind"], r["set"], r["id"])):
        print(f"| {r['id']} | {r['set']} | {'yes' if r['answerable'] else 'no'} | {r['raw']:.2f} | {r['rw']:.2f} | "
              f"{r['rw'] - r['raw']:+.2f} | {r['q']} -> {r['search_query']} |")
    if missing:
        print(f"\n{len(missing)} question(s) have no stored rewrite (failed or not run): {[p['id'] for p in missing]}")

    probes = [r for r in rows if r["kind"] == "wording_probe"]
    if probes:
        by_q = {match_key(r["q"]): r for r in rw.values()}
        print("\nWording probes vs their parent (assistant-written casual framings)")
        print("| probe | parent | parent raw | probe raw | parent rewritten | probe rewritten |")
        print("|---|---|---|---|---|---|")
        for r in probes:
            par = pool[r["parent_id"]]
            prec = by_q.get(match_key(par["q"]))
            pr_raw = g(par["q"])
            pr_rw = g(prec["search_query"]) if prec else float("nan")
            print(f"| {r['id']} | {par['id']} | {pr_raw:.2f} | {r['raw']:.2f} | {pr_rw:.2f} | {r['rw']:.2f} |")

    tune = [r for r in rows if r["kind"] == "k" and r["set"] == "tuning"]
    if tune:
        ans = [r["rw"] for r in tune if r["answerable"]]
        una = [r["rw"] for r in tune if not r["answerable"]]
        print(f"\nCutoff sweep on TUNING questions, rewritten query (answerable n={len(ans)}, unanswerable n={len(una)})")
        print("| cutoff (= an observed score) | answerable passed | unanswerable refused | wrong refusals | wrong passes |")
        print("|---|---|---|---|---|")
        for c in sorted({round(x, 2) for x in ans + una}):
            ap_ = sum(x >= c for x in ans)
            ur = sum(x < c for x in una)
            print(f"| {c:.2f} | {ap_}/{len(ans)} | {ur}/{len(una)} | {len(ans) - ap_} | {len(una) - ur} |")


if __name__ == "__main__":
    main()
