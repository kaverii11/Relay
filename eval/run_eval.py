"""The eval on REAL Groq (K, 2026-11-11, §40–41): the 20 eval questions through the production pipeline on
three retrieval settings, split BY QUESTION over two mornings so every setting sees the same days and times.

  .venv/bin/python eval/run_eval.py --plan --day 1 --settings small_pieces,medium_rerank,large_rerank
  .venv/bin/python eval/run_eval.py --go   --day 1 --settings ...      # K approves the --plan first
  .venv/bin/python eval/run_eval.py --plan --day 2 ...                  # Thursday, not before Wednesday's start time

Order: the 20 eval ids shuffled once with --seed (default 42; logged). Day 1 = positions 1-10, day 2 = 11-20.
K §41: - the order of the settings is ROTATED per question (seeded, logged in the meta file);
       - spacing after a run = that setting's estimated draft prompt x 2 (room for a redraft) against the
         7000 input-tokens-per-minute limit of 120b (and the same for 20b's understand + check), never below
         --min-gap; the limiter's own waits are logged per call and summed per row (limiter_wait_ms);
       - before EVERY question, the per-model 24 h ceiling (relay/budget.py, 170k) is checked against the
         worst case of that question on all settings (every draft redrafted); if it would not fit, the run
         stops at the question boundary, never mid-question;
       - the exact-answer cache is OFF (cache=None);
       - a per-day 429 (rpd / tpd) is saved whole (body + headers -> raw/daily429_{run}.json), not retried,
         not laddered, and the run stops at once.
Records (K items 4-5): results.csv rows (answer_grade EMPTY: K grades by hand), events (every check carries
code_ok / model_ok separately; every call_end carries cached_tokens), and raw/reading_{run}.md per
question x setting: passages, every draft's answer, claims, quotes, both verdicts, final reply, empty
"grade:" line. No expected answer, no suggested grade.
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
from relay.pipeline import Pipeline  # noqa: E402
from relay.retrieval import Retriever, cross_encoder  # noqa: E402
from relay.service import Service, write_csv  # noqa: E402

GROQ = "https://api.groq.com/openai/v1"
ITPM = 7000                 # measured hidden input-tokens-per-minute limit (both models)
REDRAFT_MEASURED = 0.30     # check replay 2026-11-10, n=10 (DECISIONS §39)


def order_ids(pool, seed):
    ids = sorted((p["id"] for p in pool if p["set"] == "eval"), key=lambda s: int(s[1:]))
    random.Random(seed).shuffle(ids)
    return ids


def setting_rotation(names, ids, seed):
    """K §41: per question, a seeded rotation of the settings order."""
    out = {}
    for i, qid in enumerate(ids):
        r = random.Random(seed * 1000 + i).randrange(len(names))
        out[qid] = names[r:] + names[:r]
    return out


def gap_seconds(draft_in, min_gap):
    """Seconds between runs so that one draft + one redraft of this setting fit under 120b's ITPM, and
    understand + check (+ one re-check) fit under 20b's."""
    big = 60 * 2 * draft_in / ITPM
    small = 60 * (UNDERSTAND_IN + 2 * CHECK_IN) / ITPM
    return max(min_gap, big, small)


def worst_tokens(draft_in_by_setting):
    """Worst case of ONE question on all settings: every draft redrafted, every check re-run."""
    s = len(draft_in_by_setting) * ((UNDERSTAND_IN + UNDERSTAND_OUT) + 2 * (CHECK_IN + CHECK_OUT))
    b = sum(2 * (d + DRAFT_OUT) for d in draft_in_by_setting.values())
    return {SMALL: s, BIG: b}


def reading_block(p, setting, rec):
    row, res, ev = rec["row"], rec["result"], rec["events"]
    ret = next((e for e in ev if e["ev"] == "retrieve"), {})
    checks = {c["round"]: c for c in ev if c["ev"] == "check"}
    drafts = [e for e in ev if e["ev"] == "draft_out"]
    calls = [(e["step"], e.get("tokens_in"), e.get("tokens_out"), e.get("cached_tokens")) for e in ev if e["ev"] == "call_end"]
    L = [f"## {p['id']} x {setting}", f"**Q:** {p['q']}", "",
         f"- reply: **{row['reply_kind']}** / {row['status']}; degrade {row['degrade_level']}; model {row['model'] or '-'}; "
         f"first token {row['first_token_ms']} ms; total {row['total_ms']} ms; calls {row['calls']}; "
         f"limiter wait {row.get('limiter_wait_ms')} ms"
         + (f"; refuse reason {res.get('refuse_reason')}" if res.get("refuse_reason") else ""),
         f"- gate: {res.get('gate')} by {res.get('gate_by')} (raw {ret.get('gate_raw')}, rewrite {ret.get('gate_rewrite')}); "
         f"query: {res.get('query')}",
         "- calls (in+out, cached): " + (", ".join(f"{s} {i}+{o} ({c} cached)" for s, i, o, c in calls) or "none"), ""]
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
            L.append("  - model check: " + ("not run" if c.get("model_ok") is None else
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
    ap.add_argument("--min-gap", type=float, default=10.0)
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
    rotation = setting_rotation(names, ids, a.seed)
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
                           setting=SETTINGS[nm], policy=pol, limiter=lim, cache=None, retriever=ret, budget=budget)
        pls[nm].keep_passages = True
        pls[nm].daily_dump = ROOT / f"raw/daily429_{run}.json"
    draft_in = {nm: round(pls[nm].draft_est(SETTINGS[nm].k)) for nm in names}
    gaps = {nm: gap_seconds(draft_in[nm], a.min_gap) for nm in names}
    wq = worst_tokens(draft_in)

    def price(r):
        n = len(qs)
        s_tok = n * len(names) * ((UNDERSTAND_IN + UNDERSTAND_OUT) + (1 + r) * (CHECK_IN + CHECK_OUT))
        b_tok = sum(n * (1 + r) * (draft_in[nm] + DRAFT_OUT) for nm in names)
        return {SMALL: {"req": n * len(names) * (2 + r), "tok": s_tok}, BIG: {"req": n * len(names) * (1 + r), "tok": b_tok}}

    exp, worst = price(REDRAFT_MEASURED), price(1.0)
    u = usage_24h()
    print(f"[eval] run {run}: target {'REAL Groq' if real else a.base_url}; day {a.day} of 2; settings {names}; "
          f"gates {', '.join(f'{nm} {SETTINGS[nm].cutoff(pol)}' for nm in names)} on {pol.gate_input}; deadline {pol.system_deadline_ms:.0f} ms; patience {a.patience:.0f} s; "
          f"check_mode {pol.check_mode}; answer cache OFF")
    print(f"  order (seed {a.seed}, all 20): {','.join(order)}")
    print(f"  today ({len(qs)} questions x {len(names)} settings = {n_runs} pipeline runs), settings rotated per question (seed {a.seed}):")
    for p in qs:
        print(f"    {p['id']:4s} {'ans' if p['ans'] else 'un '}  [{' > '.join(rotation[p['id']])}]  {p['q'][:100]}")
    print("  per run: understand (20b ~{}+{}) -> draft (120b, by setting: {}) -> check (20b ~{}+{}); every gate assumed to pass".format(
        UNDERSTAND_IN, UNDERSTAND_OUT, ", ".join(f"{nm} ~{draft_in[nm]}+{DRAFT_OUT}" for nm in names), CHECK_IN, CHECK_OUT))
    print("  spacing after a run (2 x draft prompt vs ITPM 7000, min {:.0f} s): {}".format(
        a.min_gap, ", ".join(f"{nm} {gaps[nm]:.0f} s" for nm in names)))
    print(f"  requests: at the measured redraft rate {REDRAFT_MEASURED:.0%} ~{math.ceil(exp[SMALL]['req'] + exp[BIG]['req'])}, "
          f"worst (every draft redrafted) {math.ceil(worst[SMALL]['req'] + worst[BIG]['req'])}; run cap {cap}")
    for m in (SMALL, BIG):
        print(f"  {m:22s} at 30%: {math.ceil(exp[m]['req']):3d} req / ~{exp[m]['tok']:6.0f} tok; worst {math.ceil(worst[m]['req']):3d} / "
              f"~{worst[m]['tok']:6.0f}; last 24 h {u[m]['tokens']:6d} -> after worst ~{u[m]['tokens'] + worst[m]['tok']:6.0f} "
              f"of ceiling {CEILING} ({'OK' if u[m]['tokens'] + worst[m]['tok'] <= CEILING else 'OVER: the run would stop at a question boundary'})")
    print(f"  per-question ceiling check (worst case, all settings): 20b ~{wq[SMALL]:.0f}, 120b ~{wq[BIG]:.0f} tokens")
    tot_gap = sum(gaps[nm] for nm in names) * len(qs)
    print(f"  pacing: ~{(tot_gap + 5 * n_runs) / 60:.0f} min")
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
            "setting_order_per_question": rotation, "gaps_s": gaps, "policy": pol.as_dict(), "patience_s": a.patience,
            "cap": cap, "draft_in_est": draft_in, "worst_per_question": wq,
            "started": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "ledger_before": u}
    (ROOT / f"raw/meta_{run}.json").write_text(json.dumps(meta, indent=2))
    rows, i, stopped = [], 0, None
    for p in qs:
        now = usage_24h()
        over = [m for m in (SMALL, BIG) if now[m]["tokens"] + wq[m] > CEILING]
        if over:
            stopped = (f"before {p['id']}: " + "; ".join(f"{m} {now[m]['tokens']} + worst {wq[m]:.0f} > {CEILING}" for m in over))
            print(f"  STOP at question boundary {stopped}")
            break
        for nm in rotation[p["id"]]:
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
            print(f"  {i}/{n_runs} {p['id']} {nm:14s}: {r['reply_kind']:8s} {r['status']:8s} first token {r['first_token_ms']} ms "
                  f"(limiter wait {r.get('limiter_wait_ms')} ms), calls {r['calls']}, redraft {'Y' if redraft else 'n'}, "
                  f"20b {r['tokens_in_20b']}+{r['tokens_out_20b']}, 120b {r['tokens_in_120b']}+{r['tokens_out_120b']}, "
                  f"cached {r.get('tokens_cached')}, {r['degrade_level']}", flush=True)
            hit = next((pl.daily_hit for pl in pls.values() if pl.daily_hit), None)
            if hit:
                stopped = f"per-day 429 on {hit['model']} ({hit['limit']}) at {hit['wall']}; saved raw/daily429_{run}.json"
                print(f"  STOP: {stopped}")
                break
            if budget is not None and budget.stopped:
                stopped = budget.stopped
                print(f"  STOP: {stopped}")
                break
            if i < n_runs:
                time.sleep(gaps[nm])
        if stopped:
            break
    write_csv(rows, ROOT / f"raw/results_{run}.csv")
    summ = {"n": len(rows), "answers": sum(r["reply_kind"] == "answer" for r in rows),
            "refusals": sum(r["reply_kind"] == "refusal" for r in rows), "busy": sum(r["reply_kind"] == "busy" for r in rows),
            "by_setting": {nm: sum(r["retrieval_setting"] == SETTINGS[nm].name for r in rows) for nm in names},
            "limiter_wait_ms_total": round(sum(r.get("limiter_wait_ms") or 0 for r in rows), 1),
            "tokens_cached_total": sum(r.get("tokens_cached") or 0 for r in rows),
            "requests_sent": budget.run_sent if budget else None, "stopped": stopped}
    meta.update(finished=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), summary=summ, ledger_after=usage_24h())
    (ROOT / f"raw/meta_{run}.json").write_text(json.dumps(meta, indent=2))
    print(f"[eval] {run}: {json.dumps(summ)}\n  -> raw/results_{run}.csv, raw/reading_{run}.md (grade by hand)")


if __name__ == "__main__":
    main()
