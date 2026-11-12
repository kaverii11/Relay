"""Offline tests for spend-rate pacing (K, 2026-11-12, DECISIONS §72). No Groq, no stand-in, no tokens.

  .venv/bin/python scripts/test_pacing.py

The limiter's clock is replaced by a fake one (relay.limiter.time), so refill and windows are exact.
  1. guards: window <= 0 -> never exceeded; no spend -> current 0
  2. the formula: allowed = remaining / 86,400 s (fixed 24 h horizon); exceeded = current > allowed x 1.15
  3. the window: spend older than window_s stops counting
  4. pipeline rule: pacing off = the old 20 % reserve; on = 5 % hard floor + pacing; the ladder skips 120b
     with why "daily_pacing" and drafts on 20b
  5. thread safety: settle() and check_pacing() from 8 threads at once
"""
from __future__ import annotations

import math
import sys
import threading
import time as _time
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import relay.limiter as L  # noqa: E402
from relay.config import BIG, SMALL, Policy  # noqa: E402


class FakeTime:
    """Stands in for the time module inside relay.limiter: monotonic() returns a value the test moves."""
    def __init__(self):
        self.t = 1_000.0

    def monotonic(self):
        """The fake clock."""
        return self.t


def _ok(name):
    """Print a passed test."""
    print(f"  PASS  {name}")


def fresh(clock):
    """A limiter on the fake clock with the measured limits (TPD 200k per model)."""
    L.time = clock
    return L.Limiter([SMALL, BIG])


def use_day(lim, tokens):
    """Put `tokens` into the 120b day bucket (as if spent earlier today, outside any pacing window)."""
    lim.b[BIG]["tpd"].used = float(tokens)


def test_guards(clock):
    """Division and empty-window guards."""
    lim = fresh(clock)
    over, cur, allowed = lim.check_pacing(BIG, 300, 0.15)
    assert not over and cur == 0.0 and abs(allowed - 200_000 / 86_400) < 1e-9, (over, cur, allowed)   # fresh day: 2.31
    assert lim.check_pacing(BIG, 0, 0.15) == (False, 0.0, math.inf)
    assert lim.check_pacing(BIG, -5, 0.15)[0] is False
    use_day(lim, 100_000)
    over, cur, allowed = lim.check_pacing(BIG, 300, 0.15)       # no spend logged in the window
    assert not over and cur == 0.0
    _ok("guards: fresh day allowed 2.315 tok/s (finite); window <= 0 -> off; empty window -> current 0")


def test_formula(clock):
    """allowed = remaining / 86,400 s; the 15 % tolerance."""
    lim = fresh(clock)
    use_day(lim, 100_000)                       # half the day used: 100k left / 86,400 s -> 1.1574 tok/s
    lim.settle(BIG, 0, 0, actual_in=1_000)      # 1,000 tokens in the window: 3.33 tok/s over 300 s
    over, cur, allowed = lim.check_pacing(BIG, 300, 0.15)
    assert abs(allowed - 100_000 / 86_400) < 1e-3, allowed
    assert abs(cur - 1_000 / 300) < 1e-9 and over
    lim2 = fresh(clock)                         # fresh day: 2.3148 x 1.15 = 2.662 tok/s = 798.6 tokens per 300 s
    lim2.settle(BIG, 0, 0, actual_in=790)       # 2.633 tok/s: under
    assert not lim2.check_pacing(BIG, 300, 0.15)[0]
    lim2.settle(BIG, 0, 0, actual_in=20)        # 2.70 tok/s: over
    assert lim2.check_pacing(BIG, 300, 0.15)[0]
    assert not lim2.check_pacing(SMALL, 300, 0.15)[0]           # per model
    _ok("formula: allowed = left / 86,400 s (2.315 fresh, 1.157 at half a day); 15 % tolerance edge exact")


def test_window(clock):
    """Spend older than the window drops out."""
    lim = fresh(clock)
    use_day(lim, 100_000)
    lim.settle(BIG, 0, 0, actual_in=5_000)
    assert lim.check_pacing(BIG, 300, 0.15)[0]
    clock.t += 301
    over, cur, _ = lim.check_pacing(BIG, 300, 0.15)
    assert not over and cur == 0.0
    _ok("window: a 5,000-token draft paces 120b for 300 s, then drops out of the window")


def test_pipeline_rule(clock):
    """Pipeline._big_blocked and _plan_draft, on a stub pipeline with the real methods."""
    from relay.pipeline import Pipeline
    lim = fresh(clock)

    def stub(policy):
        """Just enough of a Pipeline for the ladder methods."""
        s = SimpleNamespace(lim=lim, p=policy, setting=SimpleNamespace(k=3, fewer=(3, False), rerank=False))
        for name in ("_reserve_fraction", "_big_blocked", "_rungs", "_plan_draft"):
            setattr(s, name, getattr(Pipeline, name).__get__(s))
        return s
    off, on = stub(Policy(pacing_enabled=False)), stub(Policy())
    use_day(lim, 150_000)                       # 25 % left: above both floors
    assert off._big_blocked()[0] is False
    lim.settle(BIG, 0, 0, actual_in=3_000)      # 10 tok/s; allowed 50k / 86,400 s = 0.58 tok/s
    assert off._big_blocked()[0] is False       # pacing off ignores the rate (old behaviour)
    blocked, why, cur, allowed = on._big_blocked()
    assert blocked and why == "daily_pacing" and cur > allowed
    use_day(lim, 170_000)                       # 15 % left: under the 20 % reserve, over the 5 % floor
    assert off._big_blocked()[:2] == (True, "daily_reserve")
    use_day(lim, 195_000)                       # 2.5 % left: under the hard floor
    assert on._big_blocked()[:2] == (True, "daily_reserve")
    use_day(lim, 150_000)
    ev = []
    ctx = SimpleNamespace(question="q", deadline_ms=8000, ms=lambda: 0.0, ev=lambda name, **kw: ev.append((name, kw)))
    hits = [SimpleNamespace(chunk=SimpleNamespace(cite=lambda: "x", text="word " * 200))] * 3
    model, k, level = on._plan_draft(ctx, "q", hits)
    assert model == SMALL, (model, level)
    skips = [kw for name, kw in ev if name == "ladder_skip"]
    assert skips and all(s["why"] == "daily_pacing" and "current_tps" in s and "allowed_tps" in s for s in skips)
    _ok("pipeline: off = 20 % reserve, rate ignored; on = 5 % floor + pacing; ladder skips 120b ('daily_pacing'), drafts on 20b")


def test_threads(clock):
    """No exception or lost spend with concurrent settle / check."""
    lim = fresh(clock)
    use_day(lim, 100_000)
    go = threading.Barrier(8)

    def worker():
        """Log 500 spends of 1 token, checking pacing between each."""
        go.wait()
        for _ in range(500):
            lim.settle(BIG, 0, 0, actual_in=1)
            lim.check_pacing(BIG, 300, 0.15)
    ts = [threading.Thread(target=worker) for _ in range(8)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert sum(t for _, t in lim.spend[BIG]) == 4_000
    _ok("threads: 8 x 500 concurrent settle + check, all 4,000 tokens counted")


def main():
    """Run every test on the fake clock; restore the real time module after."""
    clock = FakeTime()
    try:
        print("pacing tests (fake clock)")
        test_guards(clock)
        test_formula(clock)
        test_window(clock)
        test_pipeline_rule(clock)
        test_threads(clock)
    finally:
        L.time = _time
    print("all passed")


if __name__ == "__main__":
    main()
