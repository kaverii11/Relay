"""Run one load scenario against the stand-in (or, at small scale, real Groq).

  .venv/bin/python load/loadgen.py steady --port 8099 [--profile afternoon|evening] [--seed 1] [--smoke --draft-share 0.6]

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
from load.mix import MIX_PATH, Sampler, draft_share, load_load_pool  # noqa: E402
from load.scenarios import CEILING_PER_MIN, MIX, PATIENCE, SCENARIOS  # noqa: E402
from relay.config import BIG, SETTINGS, SMALL, Policy  # noqa: E402
from relay.limiter import Limiter  # noqa: E402
from relay.pipeline import ExactCache, Pipeline  # noqa: E402
from relay.retrieval import Retriever, cross_encoder  # noqa: E402
from relay.service import Service, write_csv  # noqa: E402

POOL = QUESTIONS + [q for q, _ in SEED]


def schedule(sc, rng, draft_share, sampler=None, repeat_share=0.0, max_minutes=None, hot=0):
    """List of (t_seconds, question, patience_s, kind). kind = fresh | burst | burst_repeat | smoke.
    Poisson phases at QUESTION rate = draft_mult x ceiling / draft_share, plus bursts."""
    arr, t0 = [], 0.0
    for ph in sc["phases"]:
        lam = ph["draft_mult"] * CEILING_PER_MIN / draft_share / 60.0     # questions per second
        end = t0 + ph["minutes"] * 60
        t = t0
        while True:
            t += rng.expovariate(lam)
            if t >= end:
                break
            arr.append((t, None))
        t0 = end
    for bi, b in enumerate(sc.get("bursts", [])):
        arr += [(b["at_min"] * 60 + rng.uniform(0, b["within_s"]), bi) for _ in range(b["n"])]
    arr.sort()
    if max_minutes:
        arr = [a for a in arr if a[0] < max_minutes * 60]
    out, hot_sets = [], {}
    for a, bi in arr:
        pat = PATIENCE["median_s"] * math.exp(rng.gauss(0, PATIENCE["sigma"]))
        if sampler is None:                     # smoke: old CC-written pool, with replacement
            out.append((a, rng.choice(POOL), pat, "smoke"))
        elif bi is None:
            out.append((a, sampler.fresh()["q"], pat, "fresh"))
        else:
            if bi not in hot_sets:
                hot_sets[bi] = sampler.hot_set(hot)
            p, rep = sampler.burst(hot_sets[bi], repeat_share)
            out.append((a, p["q"], pat, "burst_repeat" if rep else "burst"))
    return out


def main():
    """Run one load scenario against the stand-in and write its results and events."""
    ap = argparse.ArgumentParser()
    ap.add_argument("scenario", choices=list(SCENARIOS))
    ap.add_argument("--port", type=int, default=8099)
    ap.add_argument("--profile", default="afternoon", choices=["afternoon", "evening"],
                    help="stand-in latency profile (K §25): afternoon = stage 2a, evening = stage 2b (n=20)")
    ap.add_argument("--rare", type=float, default=None, help="override the profile's measured slow-call rate")
    ap.add_argument("--setting", default="medium_rerank", choices=list(SETTINGS))
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--jitter", default="jitter", choices=["exact", "jitter"])
    ap.add_argument("--max-retries", type=int, default=None)
    ap.add_argument("--no-retry-budget", action="store_true")
    ap.add_argument("--max-minutes", type=float, default=None, help="truncate the schedule (smoke tests)")
    ap.add_argument("--tag", default="")
    ap.add_argument("--arrival-check", default="on", choices=["on", "shadow", "off"])
    ap.add_argument("--no-learn", action="store_true", help="don't learn lower limits from 429 bodies")
    ap.add_argument("--pacing", action="store_true", help="spend-rate pacing on (K §72); off = the measured 20 %% reserve")
    ap.add_argument("--smoke", action="store_true",
                    help="old CC-written pool sampled with replacement, draft_share from --draft-share (default 1)")
    ap.add_argument("--draft-share", type=float, default=None, help="override load/mix.json (smoke only)")
    a = ap.parse_args()

    sc = SCENARIOS[a.scenario]
    rng = random.Random(a.seed)
    setting = SETTINGS[a.setting]
    x, y, hot = MIX["unanswerable_share"], MIX["burst_repeat_share"], MIX["burst_hot_set"]
    if a.smoke:
        ds, sampler, mixinfo = a.draft_share or 1.0, None, {"mode": "smoke"}
    else:
        if x is None or y is None or (sc.get("bursts") and not hot):
            sys.exit("MIX X / Y / hot set not set by K (load/scenarios.py, DECISIONS §22); use --smoke for a smoke test")
        mix = json.loads(MIX_PATH.read_text())[setting.name]
        if mix["gate_threshold"] != Policy().gate_threshold:
            sys.exit(f"load/mix.json was computed at cutoff {mix['gate_threshold']}, Policy has "
                     f"{Policy().gate_threshold}: re-run load/mix.py")
        ds = draft_share(mix, x)            # phases have no repeats by design; burst repeats are extra
        sampler = Sampler(load_load_pool(), x, rng)
        mixinfo = {"mode": "pool", "pool": mix["pool"], "n_pool": mix["n_pool"], "X": x, "Y": y, "hot_set": hot,
                   "pass_answerable": mix["pass_answerable"], "pass_unanswerable": mix["pass_unanswerable"]}
    sched = schedule(sc, rng, ds, sampler, y or 0.0, a.max_minutes, hot=hot or 0)
    phase_min = sum(ph["minutes"] for ph in sc["phases"])
    mixinfo.update(draft_share_expected=round(ds, 4),
                   question_rate_per_min=[round(ph["draft_mult"] * CEILING_PER_MIN / ds, 3) for ph in sc["phases"]],
                   draft_rate_per_min_expected=[round(ph["draft_mult"] * CEILING_PER_MIN, 3) for ph in sc["phases"]],
                   arrivals_by_kind={k: sum(s[3] == k for s in sched) for k in ("fresh", "burst", "burst_repeat", "smoke")},
                   forced_repeats=sampler.forced_repeats if sampler else None, phase_minutes=phase_min)
    variant = a.tag                     # the profile is its own column, so it is not part of the variant
    name = f"{a.scenario}{('_' + variant) if variant else ''}_{a.profile}" + (f"_rare{a.rare}" if a.rare is not None else "")
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    run = f"{name}_{stamp}"
    (ROOT / "raw").mkdir(exist_ok=True)

    admin = f"http://127.0.0.1:{a.port}/admin"
    httpx.post(admin + "/reset", json={"seed": a.seed}).raise_for_status()
    cfg = {"profile": a.profile, "rare_rate": a.rare}
    if sc.get("standin_limits"):
        cfg["limits"] = sc["standin_limits"]
    httpx.post(admin + "/config", json=cfg).raise_for_status()
    for ex in sc.get("exhaust", []):
        httpx.post(admin + "/exhaust", json=ex).raise_for_status()

    # pacing off unless --pacing (K §72): Tables 2a/2b were measured with the 20 % reserve
    pol = Policy(retry_jitter=a.jitter, arrival_check=a.arrival_check, learn_limits=not a.no_learn, pacing_enabled=a.pacing)
    if a.max_retries is not None:
        pol.max_retries_per_question = a.max_retries
    if a.no_retry_budget:
        pol.retry_budget_fraction = 1e9
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
    prof_label = {"afternoon": "afternoon (2a, n=40)", "evening": "evening (2b, n=20)"}[a.profile]
    svc = Service(pl, workers=pol.workers, scenario=a.scenario, events_path=ROOT / f"raw/events_{run}.jsonl",
                  variant=variant, profile=prof_label)
    meta = {"run": run, "scenario": a.scenario, "variant": variant, "standin_profile": a.profile,
            "desc": sc["desc"], "rare_rate_override": a.rare, "seed": a.seed,
            "setting": setting.name, "policy": pol.as_dict(), "patience": PATIENCE, "n_arrivals": len(sched),
            "started": dt.datetime.now(dt.timezone.utc).isoformat(), "ceiling_per_min": CEILING_PER_MIN,
            "mix": mixinfo}
    (ROOT / f"raw/meta_{run}.json").write_text(json.dumps(meta, indent=2))
    print(f"[{run}] {len(sched)} arrivals over {sched[-1][0] / 60 if sched else 0:.1f} min; "
          f"draft share {ds:.2f} -> questions/min {mixinfo['question_rate_per_min']}, "
          f"drafts/min {mixinfo['draft_rate_per_min_expected']}; forced repeats {mixinfo['forced_repeats']}", flush=True)

    t_start = time.time()
    for i, (t, q, pat, _kind) in enumerate(sched):
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
