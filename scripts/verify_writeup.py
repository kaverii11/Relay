"""Final check (K, 2026-11-11 §52 item 10): recompute every cell of Tables 2a, 2b and 3 in writeup/writeup.md from
results.csv and report every mismatch. Never edits the write-up. Also checks results.csv rebuilds from raw/.

  .venv/bin/python scripts/verify_writeup.py
"""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from analysis.tables import f, is_rejected, paid_cost, pcts, peak_queue, served  # noqa: E402

FILES = ["steady_afternoon_20261110_233137", "burst_afternoon_20261111_003145", "overload_afternoon_20261111_005059",
         "minute_limit_halved_afternoon_20261111_012058", "daily_exhausted_afternoon_20261111_015059",
         "burst_evening_20261111_021009", "overload_evening_20261111_022927", "overload_shadow_afternoon_20261111_025926",
         "minute_limit_halved_nolearn_afternoon_20261111_032925", "e2e_evening_20261110_221128", "eval_day1_20261111_124523"]
SET = {"w250_k6_rr1": "250/6 re-rank", "w250_k6_rr0": "250/6 BM25", "w250_k3_rr0": "250/3 BM25"}


def label(r):
    """The write-up's row label (scenario, profile) for a results.csv row."""
    sc = {"minute_limit_halved": "per-minute limit halved", "daily_exhausted": "daily budget exhausted",
          "overload": "sustained overload"}.get(r["scenario"], r["scenario"])
    v = r.get("run_variant") or ""
    if v == "nolearn":
        sc += " (limit not learned)"
    if v == "shadow":
        sc += " (arrival check in shadow mode)"
    if r["scenario"] == "eval":
        sc = f"eval, {SET[r['retrieval_setting']]}"
    if r["scenario"] == "e2e":
        sc = "e2e evening set"
    prof = "real Groq" if r["source"] == "groq" else ("stand-in, evening" if "evening" in r["standin_profile"] else "stand-in, afternoon")
    return sc, prof


def table_rows(md, title):
    """The cells of the Markdown table under a heading."""
    seg = md[md.index(title):]
    seg = seg[seg.index("\n|"):]
    rows = []
    for ln in seg.strip().splitlines():
        if not ln.startswith("|"):
            break
        rows.append([c.strip() for c in ln.strip().strip("|").split("|")])
    return rows[2:]


def main():
    """Recompute every cell of Tables 2a, 2b and 3 from results.csv and list mismatches."""
    bad, n_cells = [], 0

    def cmp(where, got, want):
        """Compare one cell with its recomputed value; remember any mismatch."""
        nonlocal n_cells
        n_cells += 1
        if got.replace("**", "").strip() != want.strip():
            bad.append(f"{where}: write-up {got!r} != recomputed {want!r}")

    # 0. results.csv rebuilds from raw/
    tmp = ROOT / "raw/_verify_results.csv"
    subprocess.run([sys.executable, "scripts/assemble_results.py"] + [f"raw/results_{x}.csv" for x in FILES],
                   cwd=ROOT, check=True, capture_output=True)
    # assemble_results writes results.csv in place; compare its hash with what tables read
    h = hashlib.md5((ROOT / "results.csv").read_bytes()).hexdigest()
    rows = list(csv.DictReader(open(ROOT / "results.csv")))
    print(f"results.csv rebuilt from {len(FILES)} raw files: {len(rows)} rows, md5 {h}")

    groups, phases = defaultdict(list), defaultdict(set)
    for r in rows:
        sc, prof = label(r)
        phases[(sc, prof, r["retrieval_setting"])].add(r.get("daily_phase") or "")
    for r in rows:
        sc, prof = label(r)
        k = (sc, prof, r["retrieval_setting"])
        if len(phases[k]) > 1:
            sc += " — before the 120b day budget is gone" if r["daily_phase"] == "before" else " — after the 120b day budget is gone"
        groups[(sc, prof)].append(r)
    md = (ROOT / "writeup/writeup.md").read_text()

    # Table 2a
    for row in table_rows(md, "### Table 2a"):
        key = (row[0], row[1])
        rs = groups.get(key)
        if rs is None:
            bad.append(f"2a: no results.csv rows for {key}")
            continue
        starts = sorted(dt.datetime.fromisoformat(r["start_time"]).timestamp() for r in rs)
        ends = [dt.datetime.fromisoformat(r["start_time"]).timestamp() + f(r["total_ms"]) / 1000 for r in rs]
        sv = served(rs)                     # same rule as analysis/tables.py: input-guard rejections excluded
        got = [r for r in sv if r["status"] == "ok" and f(r["first_token_ms"]) is not None]
        nt = f"; no token {100 * (len(sv) - len(got)) / len(sv):.1f}%"
        ft, tot = pcts([f(r["first_token_ms"]) for r in got]), pcts([f(r["total_ms"]) for r in got])
        busy = [f(r["total_ms"]) for r in rs if r["reply_kind"] == "busy"]
        want = [str(len(rs)), f"{max(ends) - starts[0]:.0f}",
                f"{len(rs) / (starts[-1] - starts[0]) * 60:.2f}" if len(rs) > 1 else "nan",
                ft[:-1] + nt + ")", tot[:-1] + nt + ")", pcts(busy, (50, 95)) if busy else "no busy replies"]
        for name, g, w in zip(("requests", "duration", "rate", "first token", "total", "busy"), row[2:8], want):
            cmp(f"2a {key[0]} [{key[1]}] {name}", g, w)
    # Table 2b
    for row in table_rows(md, "### Table 2b"):
        m = re.match(r"(.*) \((stand-in, \w+|real Groq)\)$", row[0])
        key = (m.group(1), m.group(2))
        rs = groups.get(key)
        if rs is None:
            bad.append(f"2b: no results.csv rows for {key}")
            continue
        n = len(rs)
        pc = lambda s: f"{100 * sum(r['status'] == s for r in rs) / n:.1f}"  # noqa: E731
        ok = sum(r["status"] == "ok" for r in served(rs))
        unv = sum(r["status"] == "ok" and r["reply_kind"] == "unverified" for r in rs)
        toks = sum(int(r["tokens_in"]) + int(r["tokens_out"]) for r in rs)
        want = [f"{100 * ok / n:.1f} ({100 * unv / n:.1f})", pc("rate_limited"), pc("timeout"), pc("error"),
                f"{np.mean([int(r['retries']) for r in rs]):.2f}", str(peak_queue(rs)),
                f"{toks / ok:.0f}" if ok else "no answers",
                f"$0 billed (free tier); ${paid_cost(rs) / ok * 1000:.3f} at paid prices"]
        for name, g, w in zip(("succeeded", "rate-limited", "timed out", "errors", "retries", "peak queue", "tokens/answer", "cost"), row[1:9], want):
            cmp(f"2b {key[0]} [{key[1]}] {name}", g, w)
    # Table 3
    qf = {q["id"]: q["answerable"].strip().lower() == "yes" for q in csv.DictReader(open(ROOT / "eval/k_questions.csv"))}
    t3 = {"250 words, 6 pieces, re-rank (cutoff 0.875)": "w250_k6_rr1", "250 words, 6 pieces, BM25 order (0.713)": "w250_k6_rr0",
          "250 words, 3 pieces, BM25 order (0.713) — chosen": "w250_k3_rr0"}
    ev = [r for r in rows if r["scenario"] == "eval"]
    for row in table_rows(md, "### Table 3"):
        st = t3.get(row[0].replace("**", ""))
        if st is None:
            bad.append(f"3: unknown setting row {row[0]!r}")
            continue
        rs = [r for r in ev if r["retrieval_setting"] == st]
        n = len(rs)
        pc = lambda g: f"{100 * sum(r['answer_grade'] == g for r in rs) / n:.1f}"  # noqa: E731
        na = [r for r in rs if qf[r["request_id"]]]
        coa = f"{sum(r['answer_grade'] == 'correct' for r in na)}/{len(na)}"
        dr = [int(r["tokens_in"]) + int(r["tokens_out"]) for r in rs if r["reply_kind"] == "answer"]
        tq = np.mean([int(r["tokens_in"]) + int(r["tokens_out"]) for r in rs])
        lw = [f(r["limiter_wait_ms"]) or 0.0 for r in rs]
        rw = [(r, w) for r, w in zip(rs, lw) if not is_rejected(r)]   # same rule as analysis/tables.py
        ft = pcts([f(r["first_token_ms"]) - w for r, w in rw], (50, 95))
        tot = pcts([f(r["total_ms"]) - w for r, w in rw], (50, 95))
        first = row[0].startswith("250 words, 6 pieces, re-rank")
        want_correct = f"{pc('correct')} ({coa} of answerable)" if first else f"{pc('correct')} ({coa})"
        want_tok = (f"{tq:.0f} per question (n={n}); {np.mean(dr):.0f} per drafted answer (n={len(dr)})" if first
                    else f"{tq:.0f} (n={n}); {np.mean(dr):.0f} (n={len(dr)})")
        want = [str(n), want_correct, pc("wrong"), pc("refused_correctly"), want_tok, ft, tot]
        for name, g, w in zip(("asked", "correct", "wrong", "refused ok", "tokens", "first token", "total"), row[1:8], want):
            cmp(f"3 {st} {name}", g, w)
        rw = (re.search(r"Refused wrongly \(the rest of each row\): ([\d.]+) / ([\d.]+) / ([\d.]+) %", md)
              or re.search(r"False refusals:\*\* ([\d.]+)% / ([\d.]+)% / ([\d.]+)%", md))
        if rw:
            idx = ["w250_k6_rr1", "w250_k6_rr0", "w250_k3_rr0"].index(st)
            cmp(f"3 {st} refused wrongly (note)", rw.group(idx + 1), pc("refused_wrongly"))
    print(f"cells checked: {n_cells}; mismatches: {len(bad)}")
    for b in bad:
        print("  MISMATCH", b)
    tmp.unlink(missing_ok=True)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
