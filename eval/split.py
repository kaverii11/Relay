"""Seeded, stratified eval/tuning split of K's questions (K, DECISIONS §27). Run ONCE, after all
questions are written. Never fill `set` by hand.

  .venv/bin/python eval/split.py --seed SEED             # dry run: prints the split, writes nothing
  .venv/bin/python eval/split.py --seed SEED --write     # writes the `set` column into eval/k_questions.csv

Proportions of answerable, type and paper are kept by SORTED SYSTEMATIC SAMPLING (implicit
stratification): questions are sorted by (answerable, type, paper), with ties in a seeded random
order, and every (N / n_eval)-th question from a seeded random start goes to eval. Each answerable
group, each type within it, and each paper within a type then gets its share to within one question.
(The first version took quotas on the joint (paper, type, answerable) strata; with 60 questions most
strata held 1-3 questions, and the rounding left eval at 25% unanswerable vs 42% in tuning. Replaced
before any split was written; DECISIONS §27.) The same seed on the same file always gives the same split.
Refuses to overwrite a `set` column that is already filled (re-splitting after seeing results
would leak the eval set), unless --force.
"""
from __future__ import annotations

import argparse
import csv
import random
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PATH = ROOT / "eval/k_questions.csv"


def norm_paper(s):
    """'2410.00037v1.pdf' -> '2410.00037'; a cross-paper row '1706.03762v7; 2507.07955v2' -> '1706.03762+2507.07955'."""
    ids = [x.strip().removesuffix(".pdf").split("v")[0] for x in s.split(";") if x.strip()]
    return "+".join(sorted(ids)) or "(none)"


def key(r):
    """Stratum of a question: (paper, type, answerable)."""
    return (norm_paper(r["paper"]), r["type"].strip(), r["answerable"].strip().lower())


def split(rows, n_eval, seed):
    """Seeded, stratified choice of the eval questions (largest-remainder quotas)."""
    rng = random.Random(seed)
    tie = {r["id"]: rng.random() for r in sorted(rows, key=lambda r: r["id"])}
    order = sorted(rows, key=lambda r: (r["answerable"].strip().lower(), r["type"].strip(),
                                        norm_paper(r["paper"]), tie[r["id"]]))
    step = len(order) / n_eval
    start = rng.random() * step
    return {order[int(start + i * step)]["id"] for i in range(n_eval)}


def table(rows, ev, field, f):
    """Print eval vs tuning counts for one field."""
    c_e = Counter(f(r) for r in rows if r["id"] in ev)
    c_t = Counter(f(r) for r in rows if r["id"] not in ev)
    ne, nt = sum(c_e.values()), sum(c_t.values())
    print(f"\n| {field} | eval n (%) | tuning n (%) |\n|---|---|---|")
    for v in sorted(set(c_e) | set(c_t)):
        print(f"| {v} | {c_e[v]} ({100 * c_e[v] / ne:.0f}%) | {c_t[v]} ({100 * c_t[v] / nt:.0f}%) |")


def main():
    """Split the question file into eval and tuning (refuses to overwrite without --force)."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--n-eval", type=int, default=20)
    ap.add_argument("--path", type=Path, default=PATH)
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()

    with open(a.path, newline="", encoding="utf-8-sig") as fh:
        rd = csv.DictReader(fh)
        fields, rows = rd.fieldnames, list(rd)
    if any(r["set"].strip() for r in rows) and not a.force:
        sys.exit(f"{a.path}: `set` is already filled; re-splitting would leak the eval set. --force to override.")
    if len(rows) <= a.n_eval:
        sys.exit(f"only {len(rows)} questions; need more than {a.n_eval}")
    ev = split(rows, a.n_eval, a.seed)
    print(f"{a.path.name}: {len(rows)} questions -> {len(ev)} eval, {len(rows) - len(ev)} tuning (seed {a.seed})")
    table(rows, ev, "paper", lambda r: norm_paper(r["paper"]))
    table(rows, ev, "type", lambda r: r["type"].strip())
    table(rows, ev, "answerable", lambda r: r["answerable"].strip().lower())
    table(rows, ev, "gate_expected (not a stratum; shown for reference)", lambda r: r.get("gate_expected", "").strip().lower())
    print("\neval ids:", ", ".join(sorted(ev)))
    if not a.write:
        print("\n(dry run; nothing written. Add --write to set the column.)")
        return
    for r in rows:
        r["set"] = "eval" if r["id"] in ev else "tuning"
    with open(a.path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    print(f"\nwrote `set` into {a.path}")


if __name__ == "__main__":
    main()
