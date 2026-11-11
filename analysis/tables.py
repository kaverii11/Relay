"""Build Tables 2a, 2b and 3 from results.csv ONLY (so a reviewer can recompute every cell).

  .venv/bin/python analysis/tables.py results.csv

Definitions (DECISIONS §5, §7, K's percentile rule):
- Percentiles (K, 2026-11-11 §44): numpy linear interpolation over the requests that GOT A REPLY
  (status ok: answer, refusal or unverified), with n and the share of all requests that got no
  token (busy reply, gave up, error) printed in the same cell. Time to the busy reply (its own
  column) is total_ms of the busy rows. p99 is flagged † wherever n < 100.
- Total time: time until the person has the complete reply (same rows).
- daily_phase (K §44): rows are split into "before" and "after" the 120b day budget stopped serving
  drafts (reserve reached or per-day 429) when a run has both; steady becomes two rows.
- Offered rate: requests / (last start_time - first start_time) * 60.
- Duration: last (start_time + total_ms) - first start_time.
- Peak queue length (= peak WAITING, K): max overlap of waiting intervals. Each request waits
  (1) from start_time until start_time + service_start_ms (first model call sent, or cache
  answered), or until start_time + total_ms if never served; and (2) from draft_ready_ms to
  draft_sent_ms (waiting for the 120b slot) when it reached the draft.
- Tokens per answer: all tokens spent in the scenario (in + out, including failed requests)
  divided by the number of status=ok rows. Waste counts against the answers that got through.
- Cost per 1,000 answers: $0 actually billed (free tier), and the cost at Groq's paid on-demand
  prices (PRICES below, from the console model pages, fetched 2026-11-09). All tokens spent in the
  scenario (incl. failed requests) / successful (status=ok) replies x 1000, then split by
  reply_kind: drafted answers vs "the papers don't say" refusals (each kind's own tokens / its
  count), with the refusal share of ok replies beside it. Output tokens include
  reasoning tokens (Groq reports reasoning inside completion_tokens; billed as output, K's rule).
  Cached input is priced at the full input rate (we don't record cache hits per call), so the
  paid figure slightly overstates real Groq.
"""
from __future__ import annotations

import csv
import datetime as dt
import sys
from collections import defaultdict

import numpy as np

INF = float("inf")
# USD per 1M tokens, on-demand. console.groq.com/docs/model/openai/gpt-oss-120b and .../gpt-oss-20b,
# fetched 2026-11-09 (no date shown on the pages). Cached input ($0.075 / $0.037) not used.
PRICES = {"120b": {"in": 0.15, "out": 0.60}, "20b": {"in": 0.075, "out": 0.30}}


def paid_cost(rs):
    return sum(int(r[f"tokens_in_{m}"]) * PRICES[m]["in"] + int(r[f"tokens_out_{m}"]) * PRICES[m]["out"]
               for r in rs for m in PRICES) / 1e6


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
        s = "no token" if np.isinf(v) else f"{v:.0f}"
        if p >= 99 and n < 100:
            s += "†"                     # K: p99 flagged wherever n < 100 (it is the max or next to it)
        out.append(s)
    return " / ".join(out) + f" (n={n})"


def peak_queue(rows):
    ev = []
    for r in rows:
        t = dt.datetime.fromisoformat(r["start_time"]).timestamp() * 1000
        end = t + (f(r["service_start_ms"]) if f(r["service_start_ms"]) is not None else f(r["total_ms"]))
        ev += [(t, 1), (end, -1)]
        if f(r.get("draft_ready_ms")) is not None and f(r.get("draft_sent_ms")) is not None:
            ev += [(t + f(r["draft_ready_ms"]), 1), (t + f(r["draft_sent_ms"]), -1)]
    ev.sort(key=lambda e: (e[0], e[1]))       # leave (-1) before arrive (+1) at the same instant
    cur = peak = 0
    for _, d in ev:
        cur += d
        peak = max(peak, cur)
    return peak


def main(path):
    rows = list(csv.DictReader(open(path)))
    by = defaultdict(list)
    phases = defaultdict(set)
    for r in rows:
        lab = r["scenario"] + (f" [{r['run_variant']}]" if r.get("run_variant") else "")
        src = r["source"] + (f", {r['standin_profile']}" if r.get("standin_profile") else "")
        phases[(lab, src, r["retrieval_setting"])].add(r.get("daily_phase") or "")
    for r in rows:
        lab = r["scenario"] + (f" [{r['run_variant']}]" if r.get("run_variant") else "")
        src = r["source"] + (f", {r['standin_profile']}" if r.get("standin_profile") else "")
        key = (lab, src, r["retrieval_setting"])
        ph = r.get("daily_phase") or ""
        if len(phases[key]) > 1:            # K §44: split only where the run crossed the 120b day budget
            lab += f" ({ph} 120b day budget gone)"
        by[(lab, src, r["retrieval_setting"])].append(r)

    print("\nTable 2a: latency (ms). Percentiles over requests that got a reply; no-token share of all requests in the cell")
    print("| Scenario | Real or stand-in | Setting | Requests sent | Duration (s) | Offered rate (per min) | "
          "First token p50 / p95 / p99 (ms) | Total time p50 / p95 / p99 (ms) | Time to busy reply p50 / p95 (ms) |")
    print("|---|---|---|---|---|---|---|---|---|")
    for (sc, src, st), rs in sorted(by.items()):
        starts = sorted(dt.datetime.fromisoformat(r["start_time"]).timestamp() for r in rs)
        ends = [dt.datetime.fromisoformat(r["start_time"]).timestamp() + f(r["total_ms"]) / 1000 for r in rs]
        dur = max(ends) - starts[0]
        rate = len(rs) / (starts[-1] - starts[0]) * 60 if len(rs) > 1 else float("nan")
        got = [r for r in rs if r["status"] == "ok" and f(r["first_token_ms"]) is not None]
        no_tok = f"; no token {100 * (len(rs) - len(got)) / len(rs):.0f}%"
        ft = pcts([f(r["first_token_ms"]) for r in got])
        tot = pcts([f(r["total_ms"]) for r in got])
        busy = [f(r["total_ms"]) for r in rs if r["reply_kind"] == "busy"]
        tb = pcts(busy, (50, 95)) if busy else "no busy replies"
        print(f"| {sc} | {src} | {st} | {len(rs)} | {dur:.0f} | {rate:.2f} | {ft[:-1] + no_tok + ')'} | "
              f"{tot[:-1] + no_tok + ')'} | {tb} |")

    print("\nTable 2b: outcomes")
    print("| Scenario | Succeeded % | (of which unverified %) | Rate-limited % | Timed out or given up % | (error %) | Retries per request | "
          "Peak queue length | Tokens per answer | Cost per 1,000 answers |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for (sc, src, st), rs in sorted(by.items()):
        n = len(rs)
        pc = lambda s: 100 * sum(r["status"] == s for r in rs) / n  # noqa: E731
        ok = sum(r["status"] == "ok" for r in rs)
        toks = sum(int(r["tokens_in"]) + int(r["tokens_out"]) for r in rs)
        tpa = f"{toks / ok:.0f}" if ok else "no answers"
        okr = [r for r in rs if r["status"] == "ok"]
        ans = [r for r in okr if r["reply_kind"] == "answer"]
        ref = [r for r in okr if r["reply_kind"] == "refusal"]
        unv = [r for r in okr if r["reply_kind"] == "unverified"]
        per = lambda xs: f"${paid_cost(xs) / len(xs) * 1000:.3f}" if xs else "n/a"  # noqa: E731
        cost = (f"$0 billed (free tier); paid on-demand: ${paid_cost(rs) / ok * 1000:.3f} all-in "
                f"[drafted {per(ans)}, refusals {per(ref)}, unverified {per(unv)}; refusal share {100 * len(ref) / ok:.1f}%]") if ok else "no answers"
        print(f"| {sc} ({src}) | {pc('ok'):.1f} | {100 * len(unv) / n:.1f} | {pc('rate_limited'):.1f} | {pc('timeout'):.1f} | {pc('error'):.1f} | "
              f"{np.mean([int(r['retries']) for r in rs]):.2f} | {peak_queue(rs)} | {tpa} | {cost} |")

    print("\nLoad mix (extra, K §22): question rate vs draft demand, from results.csv")
    print("| Scenario | Questions/min | Drafts/min (reached the draft) | Drafts / ceiling (2.5) | "
          "Refusals % (fresh) | Unverified % | Cache hits % | Busy % |")
    print("|---|---|---|---|---|---|---|---|")
    for (sc, src, st), rs in sorted(by.items()):
        starts = sorted(dt.datetime.fromisoformat(r["start_time"]).timestamp() for r in rs)
        span = (starts[-1] - starts[0]) / 60 if len(rs) > 1 else float("nan")
        n = len(rs)
        drafts = sum(f(r.get("draft_ready_ms")) is not None for r in rs)
        cache = sum(r["degrade_level"] == "cache" for r in rs)
        fresh_ref = sum(r["reply_kind"] == "refusal" and r["degrade_level"] != "cache" for r in rs)
        busy = sum(r["reply_kind"] == "busy" for r in rs)
        unv = sum(r["reply_kind"] == "unverified" for r in rs)
        print(f"| {sc} ({src}) | {n / span:.2f} | {drafts / span:.2f} | {drafts / span / 2.5:.2f}x | "
              f"{100 * fresh_ref / n:.1f} | {100 * unv / n:.1f} | {100 * cache / n:.1f} | {100 * busy / n:.1f} |")

    graded = [r for r in rows if r["answer_grade"]]
    if graded:
        print("\nTable 3: retrieval settings (real Groq, graded rows only)")
        print("| Setting | Questions asked | Correct and cited % | Wrong % | Correctly refused % | (Refused wrongly %) | "
              "Tokens per question | Tokens per drafted answer | First token p50 / p95 (ms) | Total time p50 / p95 (ms) | "
              "Limiter wait p50 / max (ms) |")
        print("|---|---|---|---|---|---|---|---|---|---|---|")
        g = defaultdict(list)
        for r in graded:
            g[r["retrieval_setting"]].append(r)
        for st, rs in sorted(g.items()):
            n = len(rs)
            pc = lambda s: 100 * sum(r["answer_grade"] == s for r in rs) / n  # noqa: E731
            toks = np.mean([int(r["tokens_in"]) + int(r["tokens_out"]) for r in rs])
            # K §46: tokens per DRAFTED answer (reply_kind answer: a checked answer was sent), beside per question
            dr = [int(r["tokens_in"]) + int(r["tokens_out"]) for r in rs if r["reply_kind"] == "answer"]
            tda = f"{np.mean(dr):.0f} (n={len(dr)})" if dr else "n/a (n=0)"
            # K §41: Table 3 latency EXCLUDES our own limiter's planned waits; the wait is its own column
            lw = [f(r.get("limiter_wait_ms")) or 0.0 for r in rs]
            ft = pcts([None if f(r["first_token_ms"]) is None else f(r["first_token_ms"]) - w for r, w in zip(rs, lw)], (50, 95))
            tot = pcts([f(r["total_ms"]) - w if r["status"] == "ok" else None for r, w in zip(rs, lw)], (50, 95))
            wl = sorted(lw)
            print(f"| {st} | {n} | {pc('correct'):.1f} | {pc('wrong'):.1f} | {pc('refused_correctly'):.1f} | "
                  f"{pc('refused_wrongly'):.1f} | {toks:.0f} (n={n}) | {tda} | {ft} | {tot} | "
                  f"{wl[len(wl) // 2]:.0f} / {wl[-1]:.0f} (n={len(wl)}) |")


def footnote():
    print("\nPrices: Groq on-demand, USD per 1M tokens: gpt-oss-120b $0.15 in / $0.60 out; gpt-oss-20b "
          "$0.075 in / $0.30 out. Source: https://console.groq.com/docs/model/openai/gpt-oss-120b and "
          "https://console.groq.com/docs/model/openai/gpt-oss-20b, read 2026-11-09 (pages show no date). "
          "Older Groq posts list different output prices (K: $0.75 / $0.50); the console pages are used. "
          "Reasoning tokens billed as output. Cached input priced at the full input rate.")
    print("† p99 with n < 100: the top value or next to it, not a stable estimate (K).")
    print("Stand-in evening profile: fitted on 20b only (n=20 short calls); its 120b values are n=3 or borrowed "
          "from the afternoon profile (standin/calibration.json).")
    print("Arrival check expected work 3.2 s: DERIVED from the evening e2e set's answers-only first-token p50 "
          "(n=8, incl. 2 redrafts), split pre-draft 0.8 / draft 1.8 / check 0.6 s (DECISIONS §37); not a direct measurement.")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "results.csv")
    footnote()
