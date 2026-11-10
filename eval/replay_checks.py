"""Replay stored drafts through the CURRENT checker (K §37, 2026-11-10): 20b check calls only, no drafts.

  .venv/bin/python eval/replay_checks.py --build            # eval/replay_drafts.json from the evening e2e events
  .venv/bin/python eval/replay_checks.py --plan             # what would be sent (nothing sent)
  .venv/bin/python eval/replay_checks.py --go               # run (K approves the --plan first)

Each entry: {id, round, question, model, draft: {answer, claims:[{chunk, quote|quotes}], not_in_papers},
             passages: [{cite, text}], old: {code_ok, model_ok, why}, corrupt: false, note: ""}.
K adds her own corrupted drafts by copying an entry, editing draft.answer / claims and setting
"corrupt": true with a "note" saying what is wrong (the checker must reject these).
Production order is kept: the code check first (every quote word for word in its passage), the 20b model
check only when the code check passes. Output: raw/replay_checks_{stamp}.json + a table.
check_fail_rate for the stand-in = share of REAL round-0 drafts (corrupt excluded) the new checker rejects.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from relay.budget import CEILING, Budget, usage_24h  # noqa: E402
from relay.config import SETTINGS, SMALL, Policy  # noqa: E402
from relay.limiter import Limiter  # noqa: E402
from relay.pipeline import Ctx, Pipeline, est_tokens  # noqa: E402
from relay.prompts import check_messages  # noqa: E402

GROQ = "https://api.groq.com/openai/v1"
DRAFTS = ROOT / "eval/replay_drafts.json"
CHECK_OUT = 100


def build(events_path: Path):
    old = json.loads(DRAFTS.read_text()) if DRAFTS.exists() else []
    keep = [e for e in old if e.get("corrupt")]
    out = []
    for line in open(events_path):
        rec = json.loads(line)
        row, res, ev = rec["row"], rec["result"], rec["events"]
        passages = [{"cite": p["cite"], "text": p["text"]} for p in res.get("passages") or []]
        checks = {c["round"]: c for c in ev if c["ev"] == "check"}
        for d in ev:
            if d["ev"] != "draft_out":
                continue
            c = checks.get(d["round"], {})
            why = c.get("why") or ""
            out.append({"id": row["request_id"], "round": d["round"], "question": rec["question"], "model": d["model"],
                        "draft": d["draft"], "passages": passages,
                        "old": {"ok": c.get("ok"), "why": why,
                                "stage": "code" if "word-for-word" in why or "not one of the passages" in why or "No claims" in why
                                else ("model" if why else ("pass" if c.get("ok") else "?"))},
                        "corrupt": False, "note": ""})
    DRAFTS.write_text(json.dumps(out + keep, indent=2, ensure_ascii=False))
    return len(out), len(keep)


def hits_of(entry):
    return [SimpleNamespace(chunk=SimpleNamespace(text=p["text"], cite=lambda c=p["cite"]: c)) for p in entry["passages"]]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--events", type=Path, default=None, help="default: latest raw/events_e2e_evening_*.jsonl")
    ap.add_argument("--plan", action="store_true")
    ap.add_argument("--go", action="store_true")
    ap.add_argument("--gap", type=float, default=5.0)
    ap.add_argument("--base-url", default=None)
    a = ap.parse_args()
    if a.build:
        ev = a.events or sorted((ROOT / "raw").glob("events_e2e_evening_*.jsonl"))[-1]
        n, k = build(ev)
        print(f"built {DRAFTS.relative_to(ROOT)}: {n} stored drafts from {ev.name}, {k} corrupted entries kept")
        return

    entries = json.loads(DRAFTS.read_text())
    real = a.base_url is None
    pol = Policy()
    # code check first (free); model check only for those that pass it
    pl = Pipeline(base_url=a.base_url or GROQ, api_key="standin", source="groq" if real else "stand-in",
                  setting=SETTINGS["medium_rerank"], policy=pol, limiter=Limiter([SMALL]), cache=None, retriever=SimpleNamespace(chunks=[SimpleNamespace(text="x" * 1000)]))
    plan = []
    for e in entries:
        use = hits_of(e)
        if e["draft"].get("not_in_papers"):
            plan.append({"e": e, "code_ok": False, "code_why": "drafter said not_in_papers: no check in production, skipped", "est_in": 0})
            continue
        ok, why = pl._code_check(e["draft"], use)
        n_in = est_tokens(check_messages(e["question"], e["draft"].get("answer", ""), e["draft"].get("claims") or [], use)) if ok else 0
        plan.append({"e": e, "code_ok": ok, "code_why": why, "est_in": n_in})
    todo = [p for p in plan if p["code_ok"]]
    n = len(todo)
    u = usage_24h()
    print(f"[replay] {len(entries)} drafts ({sum(e['corrupt'] for e in entries)} corrupted by K); code check passes {n} "
          f"-> {n} check calls on {SMALL} ({'REAL Groq' if real else a.base_url}), effort {pol.check_effort}")
    print(f"  est tokens: ~{sum(p['est_in'] for p in todo)} in + ~{n * CHECK_OUT} out; per call in p50 "
          f"~{sorted(p['est_in'] for p in todo)[n // 2] if n else 0} (old checker p50 234); 1 call / {a.gap:.0f} s")
    print(f"  {SMALL}: last 24 h {u[SMALL]['tokens']} tok -> after ~{u[SMALL]['tokens'] + sum(p['est_in'] for p in todo) + n * CHECK_OUT} "
          f"of ceiling {CEILING}; run cap {n + 2}")
    for p in plan:
        e = p["e"]
        print(f"    {e['id']:4s} r{e['round']} {'CORRUPT ' if e['corrupt'] else '        '} old={e['old'].get('stage', '?'):5s} "
              f"code={'ok' if p['code_ok'] else 'FAIL'} {p['code_why'][:70]}")
    if not a.go:
        print("  (plan only; nothing sent.)")
        return

    if real:
        from probe.probe_groq import KEY
        pl.api_key = KEY
        pl.budget = Budget(f"replay_checks_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}", n + 2)
    results = []
    for i, p in enumerate(plan):
        e = p["e"]
        r = {"id": e["id"], "round": e["round"], "corrupt": e["corrupt"], "note": e["note"], "old": e["old"],
             "code_ok": p["code_ok"], "code_why": p["code_why"], "model_ok": None, "model_why": "", "tokens_in": 0,
             "tokens_out": 0, "work_ms": None}
        if p["code_ok"]:
            ctx = Ctx(rid=f"replay-{e['id']}-{e['round']}", question=e["question"], t0=time.perf_counter(),
                      cancel=threading.Event(), deadline_ms=60_000)
            ok, why = pl._model_check(ctx, e["draft"], hits_of(e))
            end = next((x for x in ctx.events if x["ev"] == "call_end"), {})
            r.update(model_ok=ok, model_why=why, tokens_in=end.get("tokens_in"), tokens_out=end.get("tokens_out"),
                     work_ms=end.get("work_ms"))
            if i + 1 < len(plan):
                time.sleep(a.gap)
        r["pass"] = bool(r["code_ok"] and r["model_ok"])
        results.append(r)
        print(f"  {e['id']:4s} r{e['round']} {'CORRUPT' if e['corrupt'] else '       '} -> {'PASS' if r['pass'] else 'REJECT'} "
              f"({'code' if not r['code_ok'] else 'model' if not r['model_ok'] else 'ok'}) {(r['code_why'] or r['model_why'])[:80]}"
              f"  tok {r['tokens_in']}+{r['tokens_out']} {r['work_ms']} ms", flush=True)
    real_r0 = [r for r in results if not r["corrupt"] and r["round"] == 0]
    corrupt = [r for r in results if r["corrupt"]]
    summ = {"n_drafts": len(results), "real_round0_n": len(real_r0),
            "real_round0_rejected": sum(not r["pass"] for r in real_r0),
            "check_fail_rate": round(sum(not r["pass"] for r in real_r0) / len(real_r0), 3) if real_r0 else None,
            "corrupt_n": len(corrupt), "corrupt_rejected": sum(not r["pass"] for r in corrupt),
            "check_tokens_in": [r["tokens_in"] for r in results if r["tokens_in"]],
            "check_work_ms": [r["work_ms"] for r in results if r["work_ms"]]}
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    (ROOT / f"raw/replay_checks_{stamp}.json").write_text(json.dumps({"results": results, "summary": summ}, indent=2))
    print(f"[replay] {json.dumps(summ)}\n  -> raw/replay_checks_{stamp}.json")


if __name__ == "__main__":
    main()
