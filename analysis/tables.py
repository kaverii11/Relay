"""Build Tables 2a, 2b and 3 from results.csv ONLY (so a reviewer can recompute every cell).

  .venv/bin/python analysis/tables.py results.csv

Definitions (DECISIONS §5, §7, K's percentile rule):
- Percentiles: numpy linear interpolation over ALL requests sent in the scenario. A request
  with no first token (busy reply, gave up, error) counts as +infinity, so once more than 5%
  get no token, p95 prints "no token (>X%)". n is printed beside every percentile.
- Total time: time until the person has the complete reply; no answer -> +infinity (same rule).
- Offered rate: requests / (last start_time - first start_time) * 60.
- Duration: last (start_time + total_ms) - first start_time.
- Peak queue length: max overlap of queue intervals. A request is queued from start_time
  until start_time + service_start_ms (first model call sent, or cache answered), or, if
  service_start_ms is blank (never served), until start_time + total_ms.
- Tokens per answer: all tokens spent in the scenario (in + out, including failed requests)
  divided by the number of status=ok rows. Waste counts against the answers that got through.
"""
from __future__ import annotations

import csv
import datetime as dt
import sys
from collections import defaultdict

import numpy as np

INF = float("inf")


def f(x):
    return None if x in ("", None) else float(x)


def pct_linear(sorted_vals, p):
    """Same as numpy's default 'linear' percentile, but +inf-safe (numpy does inf-inf = nan)."""
    n = len(sorted_vals)
    h = (n - 1) * p / 100
    lo, hi = int(np.floor(h)), int(np.ceil(h))
    a, b = sorted_vals[lo], sorted_vals[hi]
    if np.isinf(a) or np.isinf(b):
        return INF
    return a + (h - lo) * (b - a)


def pcts(vals, ps=(50, 95, 99)):
    a = sorted(INF if v is None else v for v in vals)
    n = len(a)
    if not n:
        return "n=0"
    out = []
    for p in ps:
        v = pct_linear(a, p)
        out.append("no token" if np.isinf(v) else f"{v:.0f}")
    return " / ".join(out) + f" (n={n})"


def peak_queue(rows):
    ev = []
    for r in rows:
        t = dt.datetime.fromisoformat(r["start_time"]).timestamp() * 1000
        end = t + (f(r["service_start_ms"]) if f(r["service_start_ms"]) is not None else f(r["total_ms"]))
        ev += [(t, 1), (end, -1)]
    ev.sort(key=lambda e: (e[0], e[1]))       # leave (-1) before arrive (+1) at the same instant
    cur = peak = 0
    for _, d in ev:
        cur += d
        peak = max(peak, cur)
    return peak


def main(path):
    rows = list(csv.DictReader(open(path)))
    by = defaultdict(list)
    for r in rows:
        by[(r["scenario"], r["source"], r["retrieval_setting"])].append(r)

    print("\nTable 2a: latency (ms). Percentiles over ALL requests; no token = +inf")
    print("| Scenario | Real or stand-in | Setting | Requests sent | Duration (s) | Offered rate (per min) | "
          "First token p50 / p95 / p99 (ms) | Total time p50 / p95 / p99 (ms) |")
    print("|---|---|---|---|---|---|---|---|")
    for (sc, src, st), rs in sorted(by.items()):
        starts = sorted(dt.datetime.fromisoformat(r["start_time"]).timestamp() for r in rs)
        ends = [dt.datetime.fromisoformat(r["start_time"]).timestamp() + f(r["total_ms"]) / 1000 for r in rs]
        dur = max(ends) - starts[0]
        rate = len(rs) / (starts[-1] - starts[0]) * 60 if len(rs) > 1 else float("nan")
        ft = [f(r["first_token_ms"]) for r in rs]
        tot = [f(r["total_ms"]) if r["status"] == "ok" else None for r in rs]
        print(f"| {sc} | {src} | {st} | {len(rs)} | {dur:.0f} | {rate:.2f} | {pcts(ft)} | {pcts(tot)} |")

    print("\nTable 2b: outcomes")
    print("| Scenario | Succeeded % | Rate-limited % | Timed out or given up % | (error %) | Retries per request | "
          "Peak queue length | Tokens per answer | Cost per 1,000 answers |")
    print("|---|---|---|---|---|---|---|---|---|")
    for (sc, src, st), rs in sorted(by.items()):
        n = len(rs)
        pc = lambda s: 100 * sum(r["status"] == s for r in rs) / n  # noqa: E731
        ok = sum(r["status"] == "ok" for r in rs)
        toks = sum(int(r["tokens_in"]) + int(r["tokens_out"]) for r in rs)
        tpa = f"{toks / ok:.0f}" if ok else "no answers"
        print(f"| {sc} ({src}) | {pc('ok'):.1f} | {pc('rate_limited'):.1f} | {pc('timeout'):.1f} | {pc('error'):.1f} | "
              f"{np.mean([int(r['retries']) for r in rs]):.2f} | {peak_queue(rs)} | {tpa} | not measured (pricing TBD) |")

    graded = [r for r in rows if r["answer_grade"]]
    if graded:
        print("\nTable 3: retrieval settings (real Groq, graded rows only)")
        print("| Setting | Questions asked | Correct and cited % | Wrong % | Correctly refused % | (Refused wrongly %) | "
              "Tokens per answer | First token p50 / p95 (ms) | Total time p50 / p95 (ms) |")
        print("|---|---|---|---|---|---|---|---|---|")
        g = defaultdict(list)
        for r in graded:
            g[r["retrieval_setting"]].append(r)
        for st, rs in sorted(g.items()):
            n = len(rs)
            pc = lambda s: 100 * sum(r["answer_grade"] == s for r in rs) / n  # noqa: E731
            toks = np.mean([int(r["tokens_in"]) + int(r["tokens_out"]) for r in rs])
            ft = pcts([f(r["first_token_ms"]) for r in rs], (50, 95))
            tot = pcts([f(r["total_ms"]) if r["status"] == "ok" else None for r in rs], (50, 95))
            print(f"| {st} | {n} | {pc('correct'):.1f} | {pc('wrong'):.1f} | {pc('refused_correctly'):.1f} | "
                  f"{pc('refused_wrongly'):.1f} | {toks:.0f} | {ft} | {tot} |")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "results.csv")
