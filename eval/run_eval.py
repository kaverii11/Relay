"""The eval on REAL Groq (K, 2026-11-11): the 20 eval questions through the production pipeline on three
retrieval settings, split BY QUESTION over two mornings so every setting sees the same days and times.

  .venv/bin/python eval/run_eval.py --plan --day 1 --settings small_pieces,medium_rerank,large_rerank
  .venv/bin/python eval/run_eval.py --go   --day 1 --settings ...      # K approves the --plan first
  .venv/bin/python eval/run_eval.py --plan --day 2 ...                  # Thursday morning, questions 11-20

Order: the 20 eval ids shuffled once with --seed (default 42; logged in the meta file). Day 1 = positions 1-10,
day 2 = 11-20. Each question runs on every setting (setting order as given) before the next question, one
call at a time, --gap seconds apart (K: 30 s, so the limiter never binds). Gate refusals cost one 20b call.
Caps (K §31): --cap requests (default 5 per pipeline run) and the per-model 170k / 24 h token ceiling.
The --plan prices the run at the measured 30 % redraft rate (replay, n=10) and at the worst case (every draft
redrafted), assuming every question passes the gate (conservative; no cross-encoder run in the plan).
Records (K items 4 and 5): results.csv rows (answer_grade EMPTY: K grades by hand), events (every check
carries code_ok / model_ok separately), and raw/reading_eval_day{d}_{stamp}.md: per question x setting the
passages, every draft's answer, claims and quotes, both verdicts, the final reply, and an empty "grade:" line.
No expected answer, no suggested grade.
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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from eval.e2e import CHECK_IN, CHECK_OUT, DRAFT_OUT, UNDERSTAND_IN, UNDERSTAND_OUT, last_event_line  # noqa: E402
from load.mix import load_pool  # noqa: E402
from relay.budget import CEILING, Budget, usage_24h  # noqa: E402
from relay.config import BIG, SETTINGS, SMALL, Policy  # noqa: E402
from relay.limiter import Limiter  # noqa: E402
from relay.pipeline import ExactCache, Pipeline  # noqa: E402
from relay.retrieval import Retriever, cross_encoder  # noqa: E402
from relay.service import Service, write_csv  # noqa: E402

GROQ = "https://api.groq.com/openai/v1"
REDRAFT_MEASURED = 0.30     # check replay 2026-11-10, n=10 (DECISIONS §39)


def order_ids(pool, seed):
    ids = sorted((p["id"] for p in pool if p["set"] == "eval"), key=lambda s: int(s[1:]))
    random.Random(seed).shuffle(ids)
    return ids


def reading_block(p, setting, rec):
    row, res, ev = rec["row"], rec["result"], rec["events"]
    ret = next((e for e in ev if e["ev"] == "retrieve"), {})
    checks = {c["round"]: c for c in ev if c["ev"] == "check"}
    drafts = [e for e in ev if e["ev"] == "draft_out"]
    L = [f"## {p['id']} x {setting}", f"**Q:** {p['q']}", "",
         f"- reply: **{row['reply_kind']}** / {row['status']}; degrade {row['degrade_level']}; model {row['model'] or '-'}; "
         f"first token {row['first_token_ms']} ms; total {row['total_ms']} ms; calls {row['calls']}"
         + (f"; refuse reason {res.get('refuse_reason')}" if res.get("refuse_reason") else ""),
         f"- gate: {res.get('gate')} by {res.get('gate_by')} (raw {ret.get('gate_raw')}, rewrite {ret.get('gate_rewrite')}); "
         f"query: {res.get('query')}", ""]
    for i, d in enumerate(drafts):
        dd, c = d["draft"], checks.get(d["round"], {})
        L.append(f"**Draft {i} ({d['model']}):** {dd.get('answer', '')}")
        if dd.get("not_in_papers"):
            L.append("  - drafter said: not in papers")
        for cl in dd.get("claims", []) or []:
            qs = cl.get("quotes") if cl.get("quotes") is not None else [cl.get("quote", "")]
            L.append(f"  - {cl.get('chunk')}: " + " | ".join(f"\"{q}\"" for q in (qs if isinstance(qs, list) else [qs])))
        if c:
            L.append(f"  - code check: {'OK' if c.get('code_ok') else 'FAIL'}" + (f" ({c['code_why']})" if c.get("code_why") else ""))
            L.append(f"  - model check: " + ("not run" if c.get("model_ok") is None else
                                               ("OK" if c["model_ok"] else f"FAIL ({c.get('model_why')})")))
        L.append("")
    L.append(f"**Final reply:** {res.get('answer', '')}")
    L.append(f"citations: {res.get('citations')}")
    L.append("")
    L.append("**Passages the drafter saw:**")
    for i, ps in enumerate(res.get("passages") or [], 1):
        L.append(f"- C{i} {ps['cite']} (bm25 {ps['bm25']}, ce {ps['ce']}): {ps['text']}")
    L += ["", "grade: ", ""]
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", action="store_true")
    ap.add_argument("--go", action="store_true")
    ap.add_argument("--day", type=int, required=True, choices=(1, 2))
    ap.add_argument("--settings", default="small_pieces,medium_rerank,large_rerank")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--per-day", type=int, default=10)
    ap.add_argument("--cap", type=int, default=None)
    ap.add_argument("--patience", type=float, default=60.0)
    ap.add_argument("--gap", type=float, default=30.0)
    ap.add_argument("--base-url", default=None)
    a = ap.parse_args()
    real = a.base_url is None
    names = [s.strip() for s in a.settings.split(",") if s.strip()]
    bad = [s for s in names if s not in SETTINGS]
    if bad:
        raise SystemExit(f"unknown settings {bad}; add them to relay/config.py SETTINGS first")
    pol = Policy()
    pool = {p["id"]: p for p in load_pool()}
    order = order_ids(pool.values(), a.seed)
    ids = order[(a.day - 1) * a.per_day: a.day * a.per_day]
    qs = [pool[i] for i in ids]
    n_runs = len(qs) * len(names)
    cap = a.cap or 5 * n_runs
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    run = f"eval_day{a.day}_{stamp}"

    cross_encoder()
    lim = Limiter([SMALL, BIG])
    budget = Budget(run, cap) if real else None
    pls = {}
    for nm in names:
        ret = Retriever(SETTINGS[nm])
        ret.search("warm-up query about attention heads")
        pls[nm] = Pipeline(base_url=a.base_url or GROQ, api_key="standin", source="groq" if real else "stand-in",
                           setting=SETTINGS[nm], policy=pol, limiter=lim, cache=ExactCache(), retriever=ret, budget=budget)
        pls[nm].keep_passages = True
    draft_in = {nm: round(pls[nm].draft_est(SETTINGS[nm].k)) for nm in names}

    def price(r):
        """tokens / requests per model for n questions on all settings at redraft rate r (all gates pass)."""
        n = len(qs)
        s_tok = n * len(names) * ((UNDERSTAND_IN + UNDERSTAND_OUT) + (1 + r) * (CHECK_IN + CHECK_OUT))
        b_tok = sum(n * (1 + r) * (draft_in[nm] + DRAFT_OUT) for nm in names)
        return {SMALL: {"req": n * len(names) * (2 + r), "tok": s_tok},
                BIG: {"req": n * len(names) * (1 + r), "tok": b_tok}}

    exp, worst = price(REDRAFT_MEASURED), price(1.0)
    u = usage_24h()
    print(f"[eval] run {run}: target {'REAL Groq' if real else a.base_url}; day {a.day} of 2; settings {names}; "
          f"gate {pol.gate_threshold} on {pol.gate_input}; deadline {pol.system_deadline_ms:.0f} ms; patience {a.patience:.0f} s; "
          f"check_mode {pol.check_mode}")
    print(f"  order (seed {a.seed}, all 20): {','.join(order)}")
    print(f"  today ({len(qs)} questions x {len(names)} settings = {n_runs} pipeline runs): {','.join(ids)}")
    for p in qs:
        print(f"    {p['id']:4s} {'ans' if p['ans'] else 'un '}  {p['type'][:28]:28s} {p['q'][:110]}")
    print("  per run: understand (20b ~{}+{}) -> draft (120b, by setting: {}) -> check (20b ~{}+{}); "
          "every gate assumed to pass".format(UNDERSTAND_IN, UNDERSTAND_OUT,
                                              ", ".join(f"{nm} ~{draft_in[nm]}+{DRAFT_OUT}" for nm in names), CHECK_IN, CHECK_OUT))
    print(f"  requests: at the measured redraft rate {REDRAFT_MEASURED:.0%} ~{math.ceil(exp[SMALL]['req'] + exp[BIG]['req'])}, "
          f"worst (every draft redrafted) {math.ceil(worst[SMALL]['req'] + worst[BIG]['req'])}; run cap {cap}")
    for m in (SMALL, BIG):
        print(f"  {m:22s} at 30%: {math.ceil(exp[m]['req']):3d} req / ~{exp[m]['tok']:6.0f} tok; worst {math.ceil(worst[m]['req']):3d} / "
              f"~{worst[m]['tok']:6.0f}; last 24 h {u[m]['tokens']:6d} -> after worst ~{u[m]['tokens'] + worst[m]['tok']:6.0f} "
              f"of ceiling {CEILING} ({'OK' if u[m]['tokens'] + worst[m]['tok'] <= CEILING else 'OVER: the run would stop early'})")
    print(f"  pacing: 1 run / {a.gap:.0f} s -> ~{n_runs * (a.gap + 5) / 60:.0f} min")
    if not a.go:
        print("  (plan only; nothing sent. Re-run with --go once approved.)")
        return

    if real:
        from probe.probe_groq import KEY
        for pl in pls.values():
            pl.api_key = KEY
    (ROOT / "raw").mkdir(exist_ok=True)
    svcs = {nm: Service(pls[nm], workers=1, scenario="eval", events_path=ROOT / f"raw/events_{run}_{nm}.jsonl",
                        variant=f"day{a.day}", profile="") for nm in names}
    md = ROOT / f"raw/reading_{run}.md"
    md.write_text(f"# eval reading file, {run}\n\nsettings {names}; gate {pol.gate_threshold} on {pol.gate_input}; "
                  f"questions {','.join(ids)}\n\n")
    meta = {"run": run, "day": a.day, "seed": a.seed, "order": order, "questions": ids, "settings": names,
            "policy": pol.as_dict(), "patience_s": a.patience, "gap_s": a.gap, "cap": cap, "draft_in_est": draft_in,
            "started": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "ledger_before": u}
    (ROOT / f"raw/meta_{run}.json").write_text(json.dumps(meta, indent=2))
    rows, i, stopped = [], 0, None
    for p in qs:
        for nm in names:
            i += 1
            svc = svcs[nm]
            svc.submit(p["id"], p["q"], a.patience)
            svc.wait_all(timeout=a.patience + 30)
            r = svc.rows[-1]
            rows.append(r)
            rec = last_event_line(ROOT / f"raw/events_{run}_{nm}.jsonl")
            with open(md, "a") as f:
                f.write(reading_block(p, nm, rec) + "\n")
            redraft = sum(e["ev"] == "draft_out" for e in rec["events"]) > 1
            print(f"  {i}/{n_runs} {p['id']} {nm:14s}: {r['reply_kind']:8s} {r['status']:8s} first token {r['first_token_ms']} ms, "
                  f"calls {r['calls']}, redraft {'Y' if redraft else 'n'}, 20b {r['tokens_in_20b']}+{r['tokens_out_20b']}, "
                  f"120b {r['tokens_in_120b']}+{r['tokens_out_120b']}, {r['degrade_level']}", flush=True)
            if budget is not None and budget.stopped:
                stopped = budget.stopped
                print(f"  STOP: {stopped}")
                break
            if i < n_runs:
                time.sleep(a.gap)
        if stopped:
            break
    write_csv(rows, ROOT / f"raw/results_{run}.csv")
    summ = {"n": len(rows), "answers": sum(r["reply_kind"] == "answer" for r in rows),
            "refusals": sum(r["reply_kind"] == "refusal" for r in rows), "busy": sum(r["reply_kind"] == "busy" for r in rows),
            "by_setting": {nm: sum(r["retrieval_setting"] == SETTINGS[nm].name for r in rows) for nm in names},
            "requests_sent": budget.run_sent if budget else None, "stopped": stopped}
    meta.update(finished=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), summary=summ, ledger_after=usage_24h())
    (ROOT / f"raw/meta_{run}.json").write_text(json.dumps(meta, indent=2))
    print(f"[eval] {run}: {json.dumps(summ)}\n  -> raw/results_{run}.csv, raw/reading_{run}.md (grade by hand)")


if __name__ == "__main__":
    main()
