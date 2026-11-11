"""Summarise real-Groq probe runs from probe/raw/*.jsonl (raw files only).

Run: .venv/bin/python analysis/probe_summary.py probe/raw/spread_*.jsonl
Percentiles use numpy's default linear interpolation and always print n.
"""
import json
import sys
from collections import defaultdict

import numpy as np


def pct(xs, ps=(50, 90, 95, 99)):
    """Percentiles of the values with n (linear interpolation)."""
    xs = np.array([x for x in xs if x is not None], dtype=float)
    if len(xs) == 0:
        return "n=0"
    return f"n={len(xs)} " + " ".join(f"p{p}={np.percentile(xs, p):.0f}" for p in ps) + f" max={xs.max():.0f}"


rows = [json.loads(l) for f in sys.argv[1:] for l in open(f)]
groups = defaultdict(list)
for r in rows:
    groups[(r["model"].split("/")[-1], r["tag"])].append(r)

for (model, tag), rs in sorted(groups.items()):
    ok = [r for r in rs if r["status"] == 200]
    print(f"\n== {model} {tag}: {len(rs)} sent, {len(ok)} ok, statuses={sorted({r['status'] for r in rs})}")
    print("  first ANSWER token ms :", pct([r["ttft_ms"] for r in ok]))
    print("  first ANY token ms    :", pct([r["first_any_ms"] for r in ok]))
    print("  total ms              :", pct([r["total_ms"] for r in ok]))
    think = [(r["ttft_ms"] - r["first_any_ms"]) for r in ok if r["ttft_ms"] and r["first_any_ms"]]
    print("  reasoning gap ms (answer - any):", pct(think, (50, 95)))
    # answer-only decode speed: answer tokens streamed between first answer token and the end
    dec = [(r["tokens_out"] - r["reasoning_tokens"]) / ((r["total_ms"] - r["ttft_ms"]) / 1000)
           for r in ok if r["ttft_ms"] and r["total_ms"] - r["ttft_ms"] > 50]
    print("  answer decode tok/s (only calls with >50 ms of answer streaming):", pct(dec, (50, 10)))
    print("  tokens in/out/reasoning mean:",
          f"{np.mean([r['tokens_in'] for r in ok]):.0f} / {np.mean([r['tokens_out'] for r in ok]):.0f} / "
          f"{np.mean([r['reasoning_tokens'] for r in ok]):.0f}")
    c = [r["ttft_ms"] for r in ok if r.get("cached_tokens")]
    u = [r["ttft_ms"] for r in ok if not r.get("cached_tokens")]
    print(f"  prompt-cache hits: {len(c)}/{len(ok)}; first-answer-token median cached={np.median(c) if c else float('nan'):.0f} "
          f"uncached={np.median(u) if u else float('nan'):.0f}")
    slow = sorted(ok, key=lambda r: -r["ttft_ms"])[:2]
    for r in slow:
        print(f"  slowest: ttft={r['ttft_ms']:.0f} any={r['first_any_ms']:.0f} reas_tok={r['reasoning_tokens']} "
              f"cached={r.get('cached_tokens')} at {r['wall'][11:19]}Z q={r['meta']['q'][:50]!r}")
