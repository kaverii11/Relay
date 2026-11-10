"""End-to-end set on REAL Groq (K §33): K's tuning questions through the production pipeline, one at a time.

  .venv/bin/python eval/e2e.py --plan --tag evening            # what would be sent; nothing sent
  .venv/bin/python eval/e2e.py --go   --tag evening            # run (K approves the --plan first)
  .venv/bin/python eval/e2e.py --plan --tag afternoon --ids Q2,Q3,...   # the SAME questions another time of day
  .venv/bin/python eval/e2e.py --go --tag smoke --base-url http://127.0.0.1:8099/v1   # stand-in dry run

Purpose (K §25): one set per time of day sets the first-token TARGET and how often that period misses it.
The deadline comes from patience (§1), not from these runs.
Questions: --n tuning rows with gate_expected=pass (the ones that reach the drafter; a refuse question
never calls 120b), answerable and unanswerable-but-pass in proportion, seeded; plus --extra more tuning
pass rows whose PREDICTED gate (max(raw, stored rewrite), K §29) clears the cutoff, so the set has enough
full-draft timings even when some seeded rows are refused at the gate (K §34: seed 7 + 2 = 10 drafts + 2
refusals). --ids replays an exact list (the Wed afternoon set must be the same 12). Eval rows are never used.
Patience is long (--patience) so nobody gives up and the whole time is measured; the busy/deadline logic
still runs with Policy.system_deadline_ms (placeholder until K sets it from these numbers).
Caps (K §31): --cap requests for the run (default 5 per question: understand, draft, check, one redraft,
one re-check) and the per-model 24 h token ceiling (relay/budget.py). The probe hard cap is not touched.
Sequential; --gap seconds between questions: 30 (K §34), because at 8 s one ~2.5k-token draft every
~11 s is ~14k input tok/min on 120b, over its 7000 ITPM, so the limiter would add waits to the timing.
The limiter wait of every call is logged (call_start.limiter_wait_s) and summed per question.
Output: raw/results_e2e_{tag}_{stamp}.csv (results.csv columns, source=groq, run_variant=tag),
        raw/events_e2e_{tag}_{stamp}.jsonl (per question: result incl. the passages the drafter saw,
        every draft's claims, each check's verdict and redraft flag, limiter waits),
        raw/answers_e2e_{tag}_{stamp}.md (the same, readable: K reads the answers tonight),
        raw/meta_e2e_{tag}_{stamp}.json.
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

from load.mix import load_pool, load_rewrites, stand_in_query  # noqa: E402
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


def _pass_cands(pool):
    return [p for p in pool if p["set"] == "tuning" and p["meta"].get("gate_expected", "").lower() == "pass"]


def pick(pool, n, seed):
    cands = _pass_cands(pool)
    rng = random.Random(seed)
    yes = [p for p in cands if p["ans"]]
    no = [p for p in cands if not p["ans"]]
    n_no = round(n * len(no) / len(cands))
    return sorted(rng.sample(yes, n - n_no) + rng.sample(no, n_no), key=lambda p: int(p["id"][1:]))


def predicted_gate(p, ret, rw):
    """max(raw, stored 20b rewrite) cross-encoder score, as production will see it (K §29). No Groq."""
    q, is_rw = stand_in_query(p, rw)
    g = ret.search(q)[1]
    return max(g, ret.search(p["q"])[1]) if is_rw else g


def add_extra(qs, pool, n_extra, seed, ret, rw, cut):
    """n_extra more tuning pass rows whose predicted gate clears the cutoff (seeded), K §34."""
    have = {p["id"] for p in qs}
    rest = [p for p in _pass_cands(pool) if p["id"] not in have and predicted_gate(p, ret, rw) >= cut]
    extra = random.Random(seed).sample(rest, min(n_extra, len(rest)))
    return sorted(qs + extra, key=lambda p: int(p["id"][1:]))


def by_ids(pool, ids):
    want = [x.strip() for x in ids.split(",") if x.strip()]
    have = {p["id"]: p for p in pool}
    missing = [x for x in want if x not in have]
    if missing:
        raise SystemExit(f"--ids: unknown {missing}")
    return [have[x] for x in want]


def last_event_line(path: Path):
    with open(path) as f:
        return json.loads(f.readlines()[-1])


def answer_md(p, rec, pred):
    """One question's block for raw/answers_*.md: the passages the drafter saw, every draft, each check."""
    row, res, ev = rec["row"], rec["result"], rec["events"]
    ret = next((e for e in ev if e["ev"] == "retrieve"), {})
    waits = [(e["step"], e.get("limiter_wait_s", 0.0), e.get("limiter_binding")) for e in ev if e["ev"] == "call_start"]
    checks = [e for e in ev if e["ev"] == "check"]
    drafts = [e for e in ev if e["ev"] == "draft_out"]
    L = [f"## {p['id']}  ({'answerable' if p['ans'] else 'unanswerable-but-pass'}; type {p['type']})",
         f"**Q:** {p['q']}", "",
         f"- reply: **{row['reply_kind']}** / {row['status']}; degrade {row['degrade_level']}; model {row['model'] or '-'}; "
         f"first token {row['first_token_ms']} ms; total {row['total_ms']} ms; calls {row['calls']}",
         f"- gate: {res.get('gate')} by {res.get('gate_by')} (raw {ret.get('gate_raw')}, rewrite {ret.get('gate_rewrite')}; "
         f"predicted {pred:.3f}); query: {res.get('query')}",
         f"- limiter waits: " + (", ".join(f"{s} {w:.2f}s ({b})" for s, w, b in waits) or "none") +
         f"; total {sum(w for _, w, _ in waits):.2f} s",
         f"- checks: " + ("; ".join(f"round {c['round']} {'OK' if c['ok'] else 'FAIL'}" + (f" ({c['why']})" if c.get('why') else "")
                                    for c in checks) or "none") + f"; **redraft: {'yes' if len(drafts) > 1 else 'no'}**",
         f"- expected (K): {p['meta'].get('expected_answer', '')}",
         f"- must_include: {p['meta'].get('must_include', '')}", ""]
    for i, d in enumerate(drafts):
        dd = d["draft"]
        L.append(f"**Draft {i} ({d['model']}):** {dd.get('answer', '')}")
        for c in dd.get("claims", []) or []:
            L.append(f"  - {c.get('chunk')}: \"{c.get('quote', '')}\"")
        if dd.get("not_in_papers"):
            L.append("  - drafter said: not in papers")
        L.append("")
    L.append(f"**Final reply:** {res.get('answer', '')}")
    L.append(f"citations: {res.get('citations')}")
    L.append("")
    L.append("**Passages the drafter saw:**")
    for i, ps in enumerate(res.get("passages") or [], 1):
        L.append(f"- C{i} {ps['cite']} (bm25 {ps['bm25']}, ce {ps['ce']}): {ps['text']}")
    L.append("")
    return "\n".join(L)


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
    ap.add_argument("--extra", type=int, default=2, help="more tuning pass rows with a predicted gate >= cutoff (K §34)")
    ap.add_argument("--ids", default=None, help="exact question list, e.g. the evening set replayed in the afternoon")
    ap.add_argument("--setting", default="medium_rerank", choices=list(SETTINGS))
    ap.add_argument("--cap", type=int, default=None, help="request cap for this run (default 5 x n)")
    ap.add_argument("--patience", type=float, default=60.0)
    ap.add_argument("--gap", type=float, default=30.0)
    ap.add_argument("--base-url", default=None, help="stand-in URL for a dry run (no ledger, no caps)")
    a = ap.parse_args()
    real = a.base_url is None
    setting, pol = SETTINGS[a.setting], Policy()
    pool = load_pool()
    rw = load_rewrites()
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    run = f"e2e_{a.tag}_{stamp}"

    ret = Retriever(setting)
    cross_encoder()
    ret.search("warm-up query about attention heads")
    if a.ids:
        qs = by_ids(pool, a.ids)
    else:
        qs = add_extra(pick(pool, a.n, a.seed), pool, a.extra, a.seed, ret, rw, pol.gate_threshold)
    pred = {p["id"]: predicted_gate(p, ret, rw) for p in qs}
    n = len(qs)
    n_pass = sum(pred[p["id"]] >= pol.gate_threshold for p in qs)
    cap = a.cap or 5 * n
    lim = Limiter([SMALL, BIG])
    budget = Budget(run, cap) if real else None
    pl = Pipeline(base_url=a.base_url or GROQ, api_key="standin", source="stand-in" if not real else "groq",
                  setting=setting, policy=pol, limiter=lim, cache=ExactCache(), retriever=ret, budget=budget)
    draft_in = round(pl.draft_est(setting.k))
    check_in = est_tokens(check_messages("x" * 120, "a" * 500, [{"chunk": "C1", "quote": "q" * 160}] * 3))
    # every question: understand (20b); only the predicted gate passes: draft (120b) + check (20b)
    exp = {SMALL: {"req": n + n_pass, "tok": n * (UNDERSTAND_IN + UNDERSTAND_OUT) + n_pass * (check_in + CHECK_OUT)},
           BIG: {"req": n_pass, "tok": n_pass * (draft_in + DRAFT_OUT)}}
    worst = {SMALL: {"req": n + 2 * n_pass, "tok": exp[SMALL]["tok"] + n_pass * (check_in + CHECK_OUT)},
             BIG: {"req": 2 * n_pass, "tok": 2 * exp[BIG]["tok"]}}

    print(f"[e2e] run {run}: target {'REAL Groq' if real else a.base_url}; setting {setting.name}; "
          f"gate {pol.gate_threshold} on {pol.gate_input}; deadline {pol.system_deadline_ms:.0f} ms (Policy); "
          f"patience {a.patience:.0f} s; reasoning_effort {pol.reasoning_effort}; check_mode {pol.check_mode}")
    print(f"  questions ({n}, tuning, gate_expected=pass, {'--ids' if a.ids else f'seed {a.seed} + {a.extra} extra'}): "
          f"{sum(p['ans'] for p in qs)} answerable + {sum(not p['ans'] for p in qs)} unanswerable-but-pass; "
          f"predicted at the gate: {n_pass} drafts + {n - n_pass} refusals")
    for p in qs:
        g = pred[p["id"]]
        print(f"    {p['id']:4s} {'ans' if p['ans'] else 'un '}  gate ~{g:6.2f} {'draft  ' if g >= pol.gate_threshold else 'REFUSE '} {p['q']}")
    print(f"  --ids {','.join(p['id'] for p in qs)}")
    print(f"  per question: understand (20b ~{UNDERSTAND_IN}+{UNDERSTAND_OUT}) -> draft (120b ~{draft_in}+{DRAFT_OUT}) "
          f"-> check (20b ~{check_in}+{CHECK_OUT}, ASSUMED: no check call measured yet); worst case +1 draft +1 check")
    print(f"  requests: expected {exp[SMALL]['req'] + exp[BIG]['req']}, worst {worst[SMALL]['req'] + worst[BIG]['req']}; "
          f"run cap {cap}" + (" (NOT counted in the 300 probe cap, K §31)" if real else ""))
    u = usage_24h()
    for m in (SMALL, BIG):
        print(f"  {m:22s} expected {exp[m]['req']:3d} req / ~{exp[m]['tok']:6d} tok; worst {worst[m]['req']:3d} / "
              f"~{worst[m]['tok']:6d}; last 24 h {u[m]['tokens']:6d} tok -> after worst ~{u[m]['tokens'] + worst[m]['tok']:6d} "
              f"of ceiling {CEILING} ({'OK' if u[m]['tokens'] + worst[m]['tok'] <= CEILING else 'OVER: the run would stop early'})")
    per_q = a.gap + 4
    print(f"  pacing: 1 question / {a.gap:.0f} s after the previous one finishes -> ~{n * per_q / 60:.0f} min; "
          f"120b input ~{draft_in * 60 / per_q:.0f} tok/min vs ITPM 7000; 20b ~{(UNDERSTAND_IN + check_in) * 60 / per_q:.0f} vs 7000")
    if not a.go:
        print("  (plan only; nothing sent. Re-run with --go once approved.)")
        return

    if real:
        from probe.probe_groq import KEY
        pl.api_key = KEY
    (ROOT / "raw").mkdir(exist_ok=True)
    pl.keep_passages = True
    events_path = ROOT / f"raw/events_{run}.jsonl"
    svc = Service(pl, workers=1, scenario="e2e", events_path=events_path, variant=a.tag, profile="")
    md = ROOT / f"raw/answers_{run}.md"
    md.write_text(f"# e2e {run}\n\nsetting {setting.name}; gate {pol.gate_threshold} on {pol.gate_input}; "
                  f"questions {','.join(p['id'] for p in qs)}\n\n")
    meta = {"run": run, "tag": a.tag, "source": pl.source, "setting": setting.name, "policy": pol.as_dict(),
            "patience_s": a.patience, "gap_s": a.gap, "cap": cap, "seed": a.seed, "extra": a.extra, "ids": a.ids,
            "questions": [p["id"] for p in qs], "predicted_gate": {k: round(v, 3) for k, v in pred.items()},
            "started": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "ledger_before": u}
    (ROOT / f"raw/meta_{run}.json").write_text(json.dumps(meta, indent=2))
    for i, p in enumerate(qs):
        svc.submit(p["id"], p["q"], a.patience)
        svc.wait_all(timeout=a.patience + 30)
        r = svc.rows[-1]
        rec = last_event_line(events_path)
        lw = sum(e.get("limiter_wait_s", 0.0) for e in rec["events"] if e["ev"] == "call_start")
        redraft = sum(e["ev"] == "draft_out" for e in rec["events"]) > 1
        with open(md, "a") as f:
            f.write(answer_md(p, rec, pred[p["id"]]) + "\n")
        print(f"  {i + 1}/{n} {p['id']}: {r['reply_kind']:8s} {r['status']:8s} first token {r['first_token_ms']} ms, "
              f"total {r['total_ms']} ms, calls {r['calls']}, limiter wait {lw:.2f} s, redraft {'Y' if redraft else 'n'}, "
              f"20b {r['tokens_in_20b']}+{r['tokens_out_20b']}, 120b {r['tokens_in_120b']}+{r['tokens_out_120b']}, "
              f"{r['degrade_level']}", flush=True)
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
            "limiter_wait_s_total": round(sum(e.get("limiter_wait_s", 0.0) for line in open(events_path)
                                              for e in json.loads(line)["events"] if e["ev"] == "call_start"), 3),
            "stopped": budget.stopped if budget else None}
    meta.update(finished=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), summary=summ,
                ledger_after=usage_24h())
    (ROOT / f"raw/meta_{run}.json").write_text(json.dumps(meta, indent=2))
    print(f"[e2e] {run}: {json.dumps(summ)}\n  -> raw/results_{run}.csv, raw/answers_{run}.md")


if __name__ == "__main__":
    main()
