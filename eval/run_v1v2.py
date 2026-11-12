"""v1 vs v2 on K's new questions (Q61-Q70), real Groq (K, 2026-11-11 §51, §59). Thursday ~13:00, after the 24 h
window frees.

  .venv/bin/python eval/run_v1v2.py --questions eval/k_questions_new.csv --plan
  .venv/bin/python eval/run_v1v2.py --questions eval/k_questions_new.csv --go      # K approves the --plan first
  then: eval/blind_reading.py <run>, K grades, eval/apply_grades.py raw/blind_reading_<run>.md --write

Arms, both 250 words / 3 pieces / BM25 order, cutoff 0.713, retrieval and gate on the piece body (§56):
  v1 = SETTINGS["chosen"],    Policy()                   (the measured system)
  v2 = SETTINGS["chosen_v2"], Policy(check_prompt="v2", draft_prompt="v2")
       (K 2026-11-11 change a: table caption + header prefix, and the drafter told to quote only the paper text after
        it; change b: number-provenance check, output cap 800)
  v3 = SETTINGS["chosen_v3a"], Policy(check_prompt="v2", draft_prompt="v2", sticky_check_fail=True)
       (K 2026-11-12 §66: v2 + change c = paper hint, append mode + change d = sticky model-check failure)
  v2 vs v1 = what a + b do; v3 vs v2 = what c + d add.
The question file is separate from eval/k_questions.csv (never in its eval/tuning split): set = "new", and an
`author` column on every row ("K", or the tool's name for questions K did not write). Same safeguards as the
eval (§41): seeded question order and per-question arm rotation, ITPM-derived spacing, worst-case 170k ceiling
check before every question (stop at a question boundary), answer cache off, a per-day 429 is saved and stops
the run. Rows are tagged by setting name (w250_k3_rr0 / w250_k3_rr0_v2 / w250_k3_rr0_v2_pha) and run_variant "v1v2".
"""
from __future__ import annotations

import argparse
import csv
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
from eval.run_eval import GROQ, REDRAFT_MEASURED, gap_seconds, reading_block, setting_rotation, worst_tokens  # noqa: E402
from load.mix import load_pool  # noqa: E402
from relay.budget import CEILING, Budget, usage_24h  # noqa: E402
from relay.config import BIG, SETTINGS, SMALL, Policy  # noqa: E402
from relay.limiter import Limiter  # noqa: E402
from relay.pipeline import Pipeline  # noqa: E402
from relay.retrieval import Retriever, cross_encoder  # noqa: E402
from relay.service import Service, write_csv  # noqa: E402

ARMS = {"chosen": lambda: Policy(pacing_enabled=False),                                            # v1
        "chosen_v2": lambda: Policy(check_prompt="v2", draft_prompt="v2", pacing_enabled=False),                         # v2 = a + b
        "chosen_v3a": lambda: Policy(check_prompt="v2", draft_prompt="v2", sticky_check_fail=True, pacing_enabled=False)}  # v3 = a-d (K §66)
# every arm pinned to pacing off (K §72): the run compares v1 / v2 / v3 on 120b drafts, as the eval was measured


def load_new(path):
    """Read the new-questions CSV; refuse ids that clash with the eval/tuning file."""
    rows = list(csv.DictReader(open(path, newline="", encoding="utf-8-sig")))
    if not rows:
        raise SystemExit(f"{path}: empty")
    bad = [r.get("id") for r in rows if not (r.get("author") or "").strip()]
    if bad:
        raise SystemExit(f"{path}: every row needs an author (K, or the tool that wrote it); missing: {bad}")
    if any((r.get("set") or "").strip() != "new" for r in rows):
        raise SystemExit(f"{path}: set must be 'new' on every row (kept out of eval/tuning)")
    old = {p["id"] for p in load_pool()}
    clash = [r["id"] for r in rows if r["id"].strip() in old]
    if clash:
        raise SystemExit(f"{path}: ids already in eval/k_questions.csv: {clash}")
    return load_pool(Path(path))


def main():
    """Plan (or run, with --go) v1 / v2 / v3 on the new questions; write results, events, reading file, meta."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--questions", required=True)
    ap.add_argument("--plan", action="store_true")
    ap.add_argument("--go", action="store_true")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--cap", type=int, default=None)
    ap.add_argument("--patience", type=float, default=60.0)
    ap.add_argument("--min-gap", type=float, default=10.0)
    ap.add_argument("--base-url", default=None)
    ap.add_argument("--spaced", action="store_true", help="stand-in only: keep the real run's spacing between runs "
                    "(without it a stand-in run fires back to back, so the limiter turns most of it away as busy)")
    a = ap.parse_args()
    real = a.base_url is None
    qs = load_new(a.questions)
    ids = sorted((p["id"] for p in qs), key=lambda s: int(s[1:]))
    random.Random(a.seed).shuffle(ids)
    pool = {p["id"]: p for p in qs}
    names = list(ARMS)
    rotation = setting_rotation(names, ids, a.seed)
    n_runs = len(ids) * len(names)
    cap = a.cap or 5 * n_runs
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    run = f"{'v1v2' if real else 'v1v2smoke'}_{stamp}"
    cross_encoder()
    lim = Limiter([SMALL, BIG])
    budget = Budget(run, cap) if real else None
    pls = {}
    for nm in names:
        ret = Retriever(SETTINGS[nm])
        ret.search("warm-up query about attention heads")
        pls[nm] = Pipeline(base_url=a.base_url or GROQ, api_key="standin", source="real" if real else "stand-in",
                           setting=SETTINGS[nm], policy=ARMS[nm](), limiter=lim, cache=None, retriever=ret, budget=budget)
        pls[nm].keep_passages = True
        pls[nm].daily_dump = ROOT / f"raw/daily429_{run}.json"
    # v2's paper hint can add one piece (append mode): plan for k + 1
    draft_in = {nm: round(pls[nm].draft_est(SETTINGS[nm].k + (1 if SETTINGS[nm].paper_hint else 0))) for nm in names}
    check_in = {"chosen": CHECK_IN, "chosen_v2": CHECK_IN + 60, "chosen_v3a": CHECK_IN + 60}          # v2 prompt is ~60 tokens longer
    check_out = {"chosen": CHECK_OUT, "chosen_v2": 300, "chosen_v3a": 300}                 # v2 replies: p50 130, p95 313 (replay §58)
    gaps = {nm: gap_seconds(draft_in[nm], a.min_gap) for nm in names}
    wq = worst_tokens(draft_in)
    wq[SMALL] += sum(2 * ((check_in[nm] - CHECK_IN) + (check_out[nm] - CHECK_OUT)) for nm in names)

    def price(r):
        """Expected requests and tokens per model for the whole run at redraft rate r."""
        n = len(ids)
        s_tok = sum(n * ((UNDERSTAND_IN + UNDERSTAND_OUT) + (1 + r) * (check_in[nm] + check_out[nm])) for nm in names)
        b_tok = sum(n * (1 + r) * (draft_in[nm] + DRAFT_OUT) for nm in names)
        return {SMALL: {"req": n * len(names) * (2 + r), "tok": s_tok}, BIG: {"req": n * len(names) * (1 + r), "tok": b_tok}}

    exp, worst = price(REDRAFT_MEASURED), price(1.0)
    u = usage_24h()
    print(f"[v1v2] run {run}: target {'REAL Groq' if real else a.base_url}; {len(ids)} questions x {len(names)} arms = "
          f"{n_runs} pipeline runs; 250/3 BM25 order, cutoff {SETTINGS["chosen"].cutoff(Policy())} (all arms), "
          f"retrieval + gate on the piece body; answer cache OFF; deadline {Policy().system_deadline_ms:.0f} ms")
    print(f"  arms: v1 = chosen (draft v1, check v1, cap 400); v2 = chosen_v2 (table prefix + draft v2 'quote only the paper text' + check v2, cap {Policy().check_max_tokens_v2}); v3 = chosen_v3a (v2 + paper hint append + sticky check failure, K §66)")
    print(f"  question order (seed {a.seed}): {','.join(ids)}; arms rotated per question")
    for q in ids:
        p = pool[q]
        print(f"    {q:4s} {'ans' if p['ans'] else 'un '} author {p['meta'].get('author', '?'):8s} [{' > '.join(rotation[q])}]  {p['q'][:90]}")
    print(f"  draft prompt est: v1 ~{draft_in['chosen']}, v2 ~{draft_in['chosen_v2']}, v3 ~{draft_in['chosen_v3a']} tokens "
          f"(v2 adds the table prefix; v3 plans one more piece); spacing {gaps['chosen']:.0f} / {gaps['chosen_v2']:.0f} / "
          f"{gaps['chosen_v3a']:.0f} s")
    print(f"  requests: at the measured redraft rate {REDRAFT_MEASURED:.0%} ~{math.ceil(exp[SMALL]['req'] + exp[BIG]['req'])}, "
          f"worst {math.ceil(worst[SMALL]['req'] + worst[BIG]['req'])}; run cap {cap}")
    for m in (SMALL, BIG):
        print(f"  {m:22s} at 30%: {math.ceil(exp[m]['req']):3d} req / ~{exp[m]['tok']:6.0f} tok; worst {math.ceil(worst[m]['req']):3d} / "
              f"~{worst[m]['tok']:6.0f}; last 24 h {u[m]['tokens']:6d} -> after worst ~{u[m]['tokens'] + worst[m]['tok']:6.0f} "
              f"of ceiling {CEILING} ({'OK' if u[m]['tokens'] + worst[m]['tok'] <= CEILING else 'OVER: stops at a question boundary'})")
    print(f"  per-question worst case (all arms): 20b ~{wq[SMALL]:.0f}, 120b ~{wq[BIG]:.0f} tokens")
    tot_gap = sum(gaps.values()) * len(ids)
    print(f"  pacing: ~{(tot_gap + 5 * n_runs) / 60:.0f} min")
    if not a.go:
        print("  (plan only; nothing sent. Re-run with --go once approved.)")
        return
    if real:
        from probe.probe_groq import KEY
        for pl in pls.values():
            pl.api_key = KEY
    svcs = {nm: Service(pls[nm], workers=1, scenario="v1v2", events_path=ROOT / f"raw/events_{run}_{nm}.jsonl",
                        variant="v1v2", profile="") for nm in names}
    md = ROOT / f"raw/reading_{run}.md"
    md.write_text(f"# v1 vs v2 reading file, {run}\n\narms {names}; questions {','.join(ids)}\n\n")
    meta = {"run": run, "seed": a.seed, "order": ids, "questions": ids, "settings": names, "completed": [],
            "questions_file": str(a.questions), "setting_order_per_question": rotation, "gaps_s": gaps,
            "policies": {nm: pls[nm].p.as_dict() for nm in names}, "cap": cap, "draft_in_est": draft_in,
            "worst_per_question": wq, "started": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "ledger_before": u}
    (ROOT / f"raw/meta_{run}.json").write_text(json.dumps(meta, indent=2))
    rows, i, stopped = [], 0, None
    for q in ids:
        p = pool[q]
        now = usage_24h()
        over = [m for m in (SMALL, BIG) if now[m]["tokens"] + wq[m] > CEILING]
        if over:
            stopped = f"before {q}: " + "; ".join(f"{m} {now[m]['tokens']} + worst {wq[m]:.0f} > {CEILING}" for m in over)
            print(f"  STOP at question boundary {stopped}")
            break
        for nm in rotation[q]:
            i += 1
            svcs[nm].submit(q, p["q"], a.patience)
            svcs[nm].wait_all(timeout=a.patience + 30)
            r = svcs[nm].rows[-1]
            rows.append(r)
            rec = last_event_line(ROOT / f"raw/events_{run}_{nm}.jsonl")
            with open(md, "a") as f:
                f.write(reading_block(p, nm, rec) + "\n")
            print(f"  {i}/{n_runs} {q} {nm:10s}: {r['reply_kind']:10s} {r['status']:8s} first token {r['first_token_ms']} ms, "
                  f"calls {r['calls']}, 20b {r['tokens_in_20b']}+{r['tokens_out_20b']}, 120b {r['tokens_in_120b']}+{r['tokens_out_120b']}",
                  flush=True)
            hit = next((pl.daily_hit for pl in pls.values() if pl.daily_hit), None)
            if hit:
                stopped = f"per-day 429 on {hit['model']} ({hit['limit']}); saved raw/daily429_{run}.json"
                break
            if budget is not None and budget.stopped:
                stopped = budget.stopped
                break
            if i < n_runs and (real or a.spaced):       # ITPM-derived spacing between runs (see gap_seconds)
                time.sleep(gaps[nm])
        if stopped:
            print(f"  STOP: {stopped}")
            break
        meta["completed"].append(q)
        (ROOT / f"raw/meta_{run}.json").write_text(json.dumps(meta, indent=2))
        write_csv(rows, ROOT / f"raw/results_{run}.csv")
    write_csv(rows, ROOT / f"raw/results_{run}.csv")
    meta.update(finished=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), stopped=stopped,
                ledger_after=usage_24h(), requests_sent=budget.run_sent if budget else None)
    (ROOT / f"raw/meta_{run}.json").write_text(json.dumps(meta, indent=2))
    # K §61: quotes taken from the repeated table prefix are reported separately (code check reason)
    for nm in names:
        ev = [json.loads(l) for l in open(ROOT / f"raw/events_{run}_{nm}.jsonl")]
        cks = [e for d in ev for e in d["events"] if e["ev"] == "check"]
        pre = [e for e in cks if (e.get("code_why") or "").find("from the repeated table prefix") >= 0]
        print(f"  {nm}: checks {len(cks)}; failed because a quote came from the table prefix: {len(pre)}; "
              f"other code-check failures: {sum(not e.get('code_ok') for e in cks) - len(pre)}; "
              f"model-check failures: {sum(e.get('code_ok') and e.get('model_ok') is False for e in cks)}")
    print(f"[v1v2] {run}: {len(rows)} rows -> raw/results_{run}.csv; then eval/blind_reading.py {run}")


if __name__ == "__main__":
    main()
