"""End-to-end set on REAL Groq (K §33): K's tuning questions through the production pipeline, one at a time.

  .venv/bin/python eval/e2e.py --plan --tag evening            # what would be sent; nothing sent
  .venv/bin/python eval/e2e.py --go   --tag evening            # run (K approves the --plan first)
  .venv/bin/python eval/e2e.py --go --tag smoke --base-url http://127.0.0.1:8099/v1   # stand-in dry run

Purpose (K §25): one set per time of day sets the first-token TARGET and how often that period misses it.
The deadline comes from patience (§1), not from these runs.
Questions: --n tuning rows with gate_expected=pass (the ones that reach the drafter; a refuse question
never calls 120b), answerable and unanswerable-but-pass in proportion, seeded. Eval rows are never used.
Patience is long (--patience) so nobody gives up and the whole time is measured; the busy/deadline logic
still runs with Policy.system_deadline_ms (placeholder until K sets it from these numbers).
Caps (K §31): --cap requests for the run (default 5 per question: understand, draft, check, one redraft,
one re-check) and the per-model 24 h token ceiling (relay/budget.py). The probe hard cap is not touched.
Sequential; --gap seconds between questions (so the RPM/TPM buckets never bind and the timing is unloaded).
Output: raw/results_e2e_{tag}_{stamp}.csv (results.csv columns, source=groq, run_variant=tag),
        raw/events_e2e_{tag}_{stamp}.jsonl, raw/meta_e2e_{tag}_{stamp}.json.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import random
import statistics as st
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from load.mix import load_pool  # noqa: E402
from relay.budget import CEILING, Budget, usage_24h  # noqa: E402
from relay.config import BIG, SETTINGS, SMALL, Policy  # noqa: E402
from relay.limiter import Limiter  # noqa: E402
from relay.pipeline import DRAFT_OUT_EST, ExactCache, Pipeline, est_tokens  # noqa: E402
from relay.prompts import check_messages  # noqa: E402
from relay.retrieval import Retriever, cross_encoder  # noqa: E402
from relay.service import Service, write_csv  # noqa: E402

GROQ = "https://api.groq.com/openai/v1"
# per-call sizes: understand measured (rewrites, n=45); draft in from the pipeline's own estimate, out measured
# (stage 2a, 258); check NOT measured yet (estimated from the prompt; labelled "assumed" in the plan)
UNDERSTAND_IN, UNDERSTAND_OUT = 415, 105
DRAFT_OUT = 260
CHECK_OUT = 60


def pick(pool, n, seed):
    cands = [p for p in pool if p["set"] == "tuning" and p["meta"].get("gate_expected", "").lower() == "pass"]
    rng = random.Random(seed)
    yes = [p for p in cands if p["ans"]]
    no = [p for p in cands if not p["ans"]]
    n_no = round(n * len(no) / len(cands))
    return sorted(rng.sample(yes, n - n_no) + rng.sample(no, n_no), key=lambda p: int(p["id"][1:]))


def pct(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, max(0, int(round(q * len(xs) + 0.5)) - 1))] if xs else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", action="store_true")
    ap.add_argument("--go", action="store_true")
    ap.add_argument("--tag", required=True, help="afternoon | evening | smoke ...; becomes run_variant")
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--setting", default="medium_rerank", choices=list(SETTINGS))
    ap.add_argument("--cap", type=int, default=None, help="request cap for this run (default 5 x n)")
    ap.add_argument("--patience", type=float, default=60.0)
    ap.add_argument("--gap", type=float, default=8.0)
    ap.add_argument("--base-url", default=None, help="stand-in URL for a dry run (no ledger, no caps)")
    a = ap.parse_args()
    real = a.base_url is None
    setting, pol = SETTINGS[a.setting], Policy()
    qs = pick(load_pool(), a.n, a.seed)
    cap = a.cap or 5 * a.n
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    run = f"e2e_{a.tag}_{stamp}"

    ret = Retriever(setting)
    cross_encoder()
    ret.search("warm-up query about attention heads")
    lim = Limiter([SMALL, BIG])
    budget = Budget(run, cap) if real else None
    pl = Pipeline(base_url=a.base_url or GROQ, api_key="standin", source="stand-in" if not real else "groq",
                  setting=setting, policy=pol, limiter=lim, cache=ExactCache(), retriever=ret, budget=budget)
    draft_in = round(pl.draft_est(setting.k))
    check_in = est_tokens(check_messages("x" * 120, "a" * 500, [{"chunk": "C1", "quote": "q" * 160}] * 3))
    n = len(qs)
    exp = {SMALL: {"req": 2 * n, "tok": n * (UNDERSTAND_IN + UNDERSTAND_OUT + check_in + CHECK_OUT)},
           BIG: {"req": n, "tok": n * (draft_in + DRAFT_OUT)}}
    worst = {SMALL: {"req": 3 * n, "tok": exp[SMALL]["tok"] + n * (check_in + CHECK_OUT)},
             BIG: {"req": 2 * n, "tok": 2 * exp[BIG]["tok"]}}

    print(f"[e2e] run {run}: target {'REAL Groq' if real else a.base_url}; setting {setting.name}; "
          f"gate {pol.gate_threshold} on {pol.gate_input}; deadline {pol.system_deadline_ms:.0f} ms (Policy); "
          f"patience {a.patience:.0f} s; reasoning_effort {pol.reasoning_effort}; check_mode {pol.check_mode}")
    print(f"  questions ({n}, tuning, gate_expected=pass, seed {a.seed}): "
          f"{sum(p['ans'] for p in qs)} answerable + {sum(not p['ans'] for p in qs)} unanswerable-but-pass")
    for p in qs:
        print(f"    {p['id']:4s} {'ans' if p['ans'] else 'un '}  {p['q']}")
    print(f"  per question: understand (20b ~{UNDERSTAND_IN}+{UNDERSTAND_OUT}) -> draft (120b ~{draft_in}+{DRAFT_OUT}) "
          f"-> check (20b ~{check_in}+{CHECK_OUT}, ASSUMED: no check call measured yet); worst case +1 draft +1 check")
    print(f"  requests: expected {exp[SMALL]['req'] + exp[BIG]['req']}, worst {worst[SMALL]['req'] + worst[BIG]['req']}; "
          f"run cap {cap}" + (" (NOT counted in the 300 probe cap, K §31)" if real else ""))
    u = usage_24h()
    for m in (SMALL, BIG):
        print(f"  {m:22s} expected {exp[m]['req']:3d} req / ~{exp[m]['tok']:6d} tok; worst {worst[m]['req']:3d} / "
              f"~{worst[m]['tok']:6d}; last 24 h {u[m]['tokens']:6d} tok -> after worst ~{u[m]['tokens'] + worst[m]['tok']:6d} "
              f"of ceiling {CEILING} ({'OK' if u[m]['tokens'] + worst[m]['tok'] <= CEILING else 'OVER: the run would stop early'})")
    print(f"  pacing: 1 question / {a.gap:.0f} s after the previous one finishes -> ~{n * (a.gap + 3) / 60:.0f} min")
    if not a.go:
        print("  (plan only; nothing sent. Re-run with --go once approved.)")
        return

    if real:
        from probe.probe_groq import KEY
        pl.api_key = KEY
    (ROOT / "raw").mkdir(exist_ok=True)
    svc = Service(pl, workers=1, scenario="e2e", events_path=ROOT / f"raw/events_{run}.jsonl", variant=a.tag, profile="")
    meta = {"run": run, "tag": a.tag, "source": pl.source, "setting": setting.name, "policy": pol.as_dict(),
            "patience_s": a.patience, "gap_s": a.gap, "cap": cap, "seed": a.seed, "questions": [p["id"] for p in qs],
            "started": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "ledger_before": u}
    (ROOT / f"raw/meta_{run}.json").write_text(json.dumps(meta, indent=2))
    for i, p in enumerate(qs):
        svc.submit(p["id"], p["q"], a.patience)
        svc.wait_all(timeout=a.patience + 30)
        r = svc.rows[-1]
        print(f"  {i + 1}/{n} {p['id']}: {r['reply_kind']:8s} {r['status']:8s} first token {r['first_token_ms']} ms, "
              f"total {r['total_ms']} ms, calls {r['calls']}, 20b {r['tokens_in_20b']}+{r['tokens_out_20b']}, "
              f"120b {r['tokens_in_120b']}+{r['tokens_out_120b']}, {r['degrade_level']}", flush=True)
        if budget is not None and budget.stopped:
            print(f"  STOP: {budget.stopped}")
            break
        if i + 1 < n:
            time.sleep(a.gap)
    write_csv(svc.rows, ROOT / f"raw/results_{run}.csv")
    rows = svc.rows
    ft = [r["first_token_ms"] for r in rows if r["first_token_ms"] is not None]
    tt = [r["total_ms"] for r in rows if r["total_ms"] is not None]
    summ = {"n": len(rows), "answers": sum(r["reply_kind"] == "answer" for r in rows),
            "refusals": sum(r["reply_kind"] == "refusal" for r in rows),
            "busy": sum(r["reply_kind"] == "busy" for r in rows), "none": sum(r["reply_kind"] == "none" for r in rows),
            "first_token_ms": {"p50": st.median(ft) if ft else None, "p95": pct(ft, 0.95), "max": max(ft) if ft else None},
            "total_ms": {"p50": st.median(tt) if tt else None, "p95": pct(tt, 0.95), "max": max(tt) if tt else None},
            "retries": sum(r["retries"] for r in rows), "requests_sent": budget.run_sent if budget else None,
            "stopped": budget.stopped if budget else None}
    meta.update(finished=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), summary=summ,
                ledger_after=usage_24h())
    (ROOT / f"raw/meta_{run}.json").write_text(json.dumps(meta, indent=2))
    print(f"[e2e] {run}: {json.dumps(summ)}\n  -> raw/results_{run}.csv")


if __name__ == "__main__":
    main()
