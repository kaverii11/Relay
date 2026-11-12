"""24 h simulation of the 120b day budget under steady traffic: 20 % reserve vs spend-rate pacing (K §72). No Groq.

  .venv/bin/python analysis/pacing_sim.py            -> stdout + raw/pacing_sim_<stamp>.md

Inputs, all from results.csv (the stand-in steady run, before the 120b day budget was gone):
  - arrival rate of questions that reach the draft (drafts per minute over the run)
  - 120b tokens per drafted request (tokens_in_120b + tokens_out_120b, redrafts included), sampled with replacement
Each arrival asks the real Pipeline._big_blocked rule (on a stub, fake clock) whether 120b may draft; if yes its
tokens go into the limiter's day bucket and spend history, otherwise it drafts on 20b (not modelled further).
The day bucket refills continuously at 200k / 86,400 s (our model of Groq's TPD). Poisson arrivals, seed 42.
What it does NOT model: 20b's own day budget, the per-minute limits, the deadline, cache hits.
"""
from __future__ import annotations

import csv
import datetime as dt
import random
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import relay.limiter as L  # noqa: E402
from relay.config import BIG, SMALL, Policy  # noqa: E402
from relay.pipeline import Pipeline  # noqa: E402


class FakeTime:
    """Replaces the time module inside relay.limiter."""
    t = 0.0

    def monotonic(self):
        """The simulated clock (seconds)."""
        return self.t


def steady_inputs():
    """(drafts per minute, list of 120b tokens per 120b-drafted request) from the steady run in results.csv."""
    rows = [r for r in csv.DictReader(open(ROOT / "results.csv"))
            if r["scenario"] == "steady" and not r["run_variant"] and r["daily_phase"] == "before"]
    ts = sorted(dt.datetime.fromisoformat(r["start_time"]).timestamp() for r in rows)
    drafts = [r for r in rows if r.get("draft_ready_ms")]
    tok = [int(r["tokens_in_120b"]) + int(r["tokens_out_120b"]) for r in rows if int(r["tokens_in_120b"] or 0) > 0]
    return len(drafts) / ((ts[-1] - ts[0]) / 60), tok, len(rows)


def simulate(policy, rate_per_min, tokens, hours=24, seed=42):
    """Run one day; return per-hour 120b / 20b draft counts and the first time 120b was refused."""
    clock = FakeTime()
    L.time = clock
    lim = L.Limiter([SMALL, BIG])
    pl = SimpleNamespace(lim=lim, p=policy)
    for name in ("_reserve_fraction", "_big_blocked"):
        setattr(pl, name, getattr(Pipeline, name).__get__(pl))
    rnd = random.Random(seed)
    per_h = [[0, 0] for _ in range(hours)]
    first_skip, why_first, t = None, None, 0.0
    while True:
        t += rnd.expovariate(rate_per_min / 60)
        if t >= hours * 3600:
            break
        clock.t = t
        blocked, why, _, _ = pl._big_blocked()
        h = int(t // 3600)
        if blocked:
            per_h[h][1] += 1
            if first_skip is None:
                first_skip, why_first = t, why
            continue
        n = rnd.choice(tokens)
        lim.reserve(BIG, n, 0)                    # into every bucket, as acquire() does
        lim.settle(BIG, 0, 0, actual_in=n)        # and into the spend history pacing reads
        per_h[h][0] += 1
    return per_h, first_skip, why_first, lim.daily_fraction_left(BIG)


def main():
    """Three policies, one table; also written to raw/."""
    rate, tok, n = steady_inputs()
    mean_tok = sum(tok) / len(tok)
    arms = {"20 % reserve (pacing off, as measured)": Policy(pacing_enabled=False),
            "pacing, K's values (300 s, 15 %, 5 % floor)": Policy(),
            "pacing, window 1,800 s (sensitivity)": Policy(pacing_window_s=1800.0)}
    out = [f"# 120b day budget, 24 h simulation ({dt.datetime.now().isoformat(timespec='minutes')}); no Groq", "",
           f"Steady run (results.csv, before phase, {n} requests): {rate:.2f} drafts/min; 120b tokens per drafted "
           f"request mean {mean_tok:.0f} (n={len(tok)}). Sustainable 120b rate: 200,000 / 86,400 = 2.31 tok/s "
           f"= {200000 / mean_tok:.0f} drafts/day; demand: {rate * 1440:.0f} drafts/day.", "",
           "| Policy | 120b first refused | 120b drafts in 24 h | share of drafts on 120b | 120b drafts per 4 h block | day left at 24 h |",
           "|---|---|---|---|---|---|"]
    for name, pol in arms.items():
        per_h, first, why, left = simulate(pol, rate, tok)
        big = sum(x[0] for x in per_h)
        tot = big + sum(x[1] for x in per_h)
        blocks = " / ".join(str(sum(x[0] for x in per_h[i:i + 4])) for i in range(0, 24, 4))
        fs = "never" if first is None else f"{first / 60:.0f} min ({why})"
        out.append(f"| {name} | {fs} | {big} | {100 * big / tot:.1f}% | {blocks} | {100 * left:.0f}% |")
    txt = "\n".join(out)
    print(txt)
    (ROOT / f"raw/pacing_sim_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.md").write_text(txt + "\n")


if __name__ == "__main__":
    main()
