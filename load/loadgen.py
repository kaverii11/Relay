"""Run one load scenario against the stand-in (or, at small scale, real Groq).

  .venv/bin/python load/loadgen.py steady --port 8099 --rare 0.05 [--time-scale 1] [--seed 1]

Open-loop: the full arrival schedule is drawn up front from a seeded RNG and saved to
raw/, then each question is submitted at its arrival time whether or not earlier ones
have finished. A closed loop (wait for an answer before asking again) would hide overload.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import random
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from eval.latency_questions import QUESTIONS  # noqa: E402
from eval.seed_questions import SEED  # noqa: E402
from load.scenarios import CEILING_PER_MIN, PATIENCE, SCENARIOS  # noqa: E402
from relay.config import BIG, SETTINGS, SMALL, Policy  # noqa: E402
from relay.limiter import Limiter  # noqa: E402
from relay.pipeline import ExactCache, Pipeline  # noqa: E402
from relay.retrieval import Retriever, cross_encoder  # noqa: E402
from relay.service import Service, write_csv  # noqa: E402

POOL = QUESTIONS + [q for q, _ in SEED]


def schedule(sc, rng, max_minutes=None):
    """List of (t_seconds, question, patience_s). Poisson phases + bursts."""
    arr, t0 = [], 0.0
    for ph in sc["phases"]:
        lam = ph["rate_mult"] * CEILING_PER_MIN / 60.0        # per second
        end = t0 + ph["minutes"] * 60
        t = t0
        while True:
            t += rng.expovariate(lam)
            if t >= end:
                break
            arr.append(t)
        t0 = end
    for b in sc.get("bursts", []):
        arr += [b["at_min"] * 60 + rng.uniform(0, b["within_s"]) for _ in range(b["n"])]
    arr.sort()
    if max_minutes:
        arr = [a for a in arr if a < max_minutes * 60]
    out = []
    for a in arr:
        pat = PATIENCE["median_s"] * math.exp(rng.gauss(0, PATIENCE["sigma"]))
        out.append((a, rng.choice(POOL), pat))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("scenario", choices=list(SCENARIOS))
    ap.add_argument("--port", type=int, default=8099)
    ap.add_argument("--rare", type=float, default=0.05)
    ap.add_argument("--setting", default="medium_rerank", choices=list(SETTINGS))
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--jitter", default="jitter", choices=["exact", "jitter"])
    ap.add_argument("--max-retries", type=int, default=None)
    ap.add_argument("--no-retry-budget", action="store_true")
    ap.add_argument("--max-minutes", type=float, default=None, help="truncate the schedule (smoke tests)")
    ap.add_argument("--tag", default="")
    ap.add_argument("--arrival-check", default="on", choices=["on", "shadow", "off"])
    ap.add_argument("--no-learn", action="store_true", help="don't learn lower limits from 429 bodies")
    a = ap.parse_args()

    sc = SCENARIOS[a.scenario]
    rng = random.Random(a.seed)
    sched = schedule(sc, rng, a.max_minutes)
    name = f"{a.scenario}{('_' + a.tag) if a.tag else ''}_rare{a.rare}"
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    run = f"{name}_{stamp}"
    (ROOT / "raw").mkdir(exist_ok=True)

    admin = f"http://127.0.0.1:{a.port}/admin"
    httpx.post(admin + "/reset", json={"seed": a.seed}).raise_for_status()
    cfg = {"rare_rate": a.rare}
    if sc.get("standin_limits"):
        cfg["limits"] = sc["standin_limits"]
    httpx.post(admin + "/config", json=cfg).raise_for_status()
    for ex in sc.get("exhaust", []):
        httpx.post(admin + "/exhaust", json=ex).raise_for_status()

    pol = Policy(retry_jitter=a.jitter, arrival_check=a.arrival_check, learn_limits=not a.no_learn)
    if a.max_retries is not None:
        pol.max_retries_per_question = a.max_retries
    if a.no_retry_budget:
        pol.retry_budget_fraction = 1e9
    setting = SETTINGS[a.setting]
    # Our limiter knows the limits we'd know in production. In the halved scenario it is NOT told:
    # limits "change without notice" (brief); it learns only from headers and 429s.
    lim = Limiter([SMALL, BIG])
    if sc.get("exhaust"):
        # Production would know today's usage from its own accounting; mirror the stand-in's state.
        st = httpx.get(admin + "/stats").json()["remaining"]
        for m in (SMALL, BIG):
            b = lim.b[m]["tpd"]
            b.used = b.limit - st[m]["tpd"]
    ret = Retriever(setting)
    cross_encoder()
    ret.search("warm-up query about attention heads")   # first inference is ~4x slower (723 vs 181 ms, smoke run)
    pl = Pipeline(base_url=f"http://127.0.0.1:{a.port}/v1", api_key="standin", source="stand-in",
                  setting=setting, policy=pol, limiter=lim, cache=ExactCache(), retriever=ret)
    svc = Service(pl, workers=pol.workers, scenario=a.scenario, events_path=ROOT / f"raw/events_{run}.jsonl")
    meta = {"run": run, "scenario": a.scenario, "desc": sc["desc"], "rare_rate": a.rare, "seed": a.seed,
            "setting": setting.name, "policy": pol.as_dict(), "patience": PATIENCE, "n_arrivals": len(sched),
            "started": dt.datetime.now(dt.timezone.utc).isoformat(), "ceiling_per_min": CEILING_PER_MIN}
    (ROOT / f"raw/meta_{run}.json").write_text(json.dumps(meta, indent=2))
    print(f"[{run}] {len(sched)} arrivals over {sched[-1][0] / 60 if sched else 0:.1f} min", flush=True)

    t_start = time.time()
    for i, (t, q, pat) in enumerate(sched):
        delay = t_start + t - time.time()
        if delay > 0:
            time.sleep(delay)
        svc.submit(f"{a.scenario}-{a.seed}-{i:04d}", q, pat)
        if i % 25 == 0:
            print(f"  t={t / 60:5.1f}min submitted {i + 1}/{len(sched)} done={len(svc.rows)}", flush=True)
    svc.wait_all(timeout=600)
    write_csv(svc.rows, ROOT / f"raw/results_{run}.csv")
    stats = httpx.get(admin + "/stats").json()
    meta.update(finished=dt.datetime.now(dt.timezone.utc).isoformat(), standin_stats=stats, n_rows=len(svc.rows))
    (ROOT / f"raw/meta_{run}.json").write_text(json.dumps(meta, indent=2))
    print(f"[{run}] done: {len(svc.rows)} rows -> raw/results_{run}.csv; stand-in {stats}", flush=True)


if __name__ == "__main__":
    main()
