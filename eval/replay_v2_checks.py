"""Replay stored drafts through the v2 model check (K §51 b, §54) on gpt-oss-20b. No 120b calls.

  .venv/bin/python eval/replay_v2_checks.py --plan
  .venv/bin/python eval/replay_v2_checks.py --go          # K approves the --plan first

Drafts: every eval draft with claims (eval_day1_20261111_124523 event logs; drafter "not in papers" drafts have
nothing to check), graded by K: a SENT draft carries the row's grade, a REJECTED draft K's "draft N grade";
plus K's 4 corrupted drafts (eval/replay_drafts.json, expected REJECT).
Passages: the v2 version of the SAME pieces (v2 keeps v1's windows and adds the table prefix), matched by the
v1 text, so the checker sees what v2 would show. Every draft goes to the model check, including the 8 the
code check rejected (production would never send those to it), so the counts are reported for the 27
code-passing drafts (what production would see) and for all.
Report vs K's grades: wrong drafts caught, correct drafts rejected, corrupted rejected. v1 verdicts (measured
in the eval run) are printed beside for comparison.
Output: raw/replay_v2_checks_{stamp}.json (each verdict, the checker's "numbers" list, tokens, ms).
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

from eval.e2e import CHECK_OUT  # noqa: E402
from relay.budget import CEILING, Budget, usage_24h  # noqa: E402
from relay.config import SETTINGS, SMALL, Policy  # noqa: E402
from relay.ingest import load  # noqa: E402
from relay.limiter import Limiter  # noqa: E402
from relay.pipeline import Ctx, Pipeline, est_tokens  # noqa: E402
from relay.prompts import check_messages  # noqa: E402

GROQ = "https://api.groq.com/openai/v1"
POST_HOC = ("POST-HOC: the v2 check prompt was written after seeing these failures (K's grades of the eval drafts); "
            "these counts are not an independent test of it.")
RUN = "eval_day1_20261111_124523"


def v2_hits(passages, v1_by_text, v2_by_id):
    """The same passages as v2 pieces (with the table prefix)."""
    out, missing = [], 0
    for p in passages:
        cid = v1_by_text.get(p["text"])
        ch = v2_by_id.get(cid) if cid else None
        if ch is None:
            missing += 1
            ch = SimpleNamespace(text=p["text"], prefix=None, body=p["text"], cite=lambda c=p["cite"]: c)
        out.append(SimpleNamespace(chunk=ch))
    return out, missing


def entries():
    """Every eval draft that reached the model check, with its grade, plus corrupted ones."""
    v1 = load(ROOT / "data/chunks_w250.jsonl")
    v2 = {c.id: c for c in load(ROOT / "data/chunks_w250_v2.jsonl")}
    v1_by_text = {c.text: c.id for c in v1}
    meta = json.loads((ROOT / f"raw/meta_{RUN}.json").read_text())
    key = json.loads((ROOT / f"raw/blind_key_{RUN}.json").read_text())["key"]
    bid = {(v["question"], v["setting"]): b for b, v in key.items()}
    notes = json.loads((ROOT / f"raw/grades_{RUN}.json").read_text())
    import csv
    grade = {(r["request_id"], r["retrieval_setting"]): r for r in csv.DictReader(open(ROOT / f"raw/results_{RUN}.csv"))}
    out = []
    for nm in meta["settings"]:
        for ln in open(ROOT / f"raw/events_{RUN}_{nm}.jsonl"):
            d = json.loads(ln)
            qid = d["row"]["request_id"]
            row = grade[(qid, SETTINGS[nm].name)]
            checks = {e["round"]: e for e in d["events"] if e["ev"] == "check"}
            sent = next((k for k, c in checks.items() if c.get("ok")), None) if row["reply_kind"] == "answer" else None
            hits, miss = v2_hits(d["result"].get("passages") or [], v1_by_text, v2)
            for e in d["events"]:
                if e["ev"] != "draft_out" or e["draft"].get("not_in_papers") or not e["draft"].get("claims"):
                    continue
                c = checks.get(e["round"], {})
                g = row["answer_grade"] if e["round"] == sent else \
                    notes.get(f"{qid} x {nm}", {}).get("drafts", {}).get(str(e["round"]), {}).get("label", "ungraded")
                out.append({"tag": f"{bid[(qid, nm)]} d{e['round']}", "question": d["question"], "draft": e["draft"],
                            "hits": hits, "missing_v2": miss, "grade": g, "corrupt": False,
                            "v1_code_ok": c.get("code_ok"), "v1_model_ok": c.get("model_ok")})
    for e in json.loads((ROOT / "eval/replay_drafts.json").read_text()):
        if e.get("corrupt"):
            hits, miss = v2_hits(e["passages"], v1_by_text, v2)
            out.append({"tag": f"CORRUPT {e['id']} r{e['round']}", "question": e["question"], "draft": e["draft"],
                        "hits": hits, "missing_v2": miss, "grade": "wrong (corrupted, expected REJECT)", "corrupt": True,
                        "v1_code_ok": None, "v1_model_ok": None})
    return out


def main():
    """Plan or run the v2 check on the stored eval drafts (20b only) and report vs the grades."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", action="store_true")
    ap.add_argument("--go", action="store_true")
    ap.add_argument("--gap", type=float, default=8.0)
    a = ap.parse_args()
    es = entries()
    pol = Policy(check_prompt="v2")
    pl = Pipeline(base_url=GROQ, api_key="x", source="real", setting=SETTINGS["chosen_v2"], policy=pol,
                  limiter=Limiter([SMALL]), cache=None, retriever=SimpleNamespace(chunks=[SimpleNamespace(text="x" * 1000)]))
    for e in es:
        e["est_in"] = est_tokens(check_messages(e["question"], e["draft"].get("answer", ""), e["draft"]["claims"], e["hits"], variant="v2"))
        e["code_ok"], e["code_why"] = pl._code_check(e["draft"], e["hits"])
    n = len(es)
    tin = sum(e["est_in"] for e in es)
    u = usage_24h()
    print(f"[replay v2 check] {n} drafts: {sum(not e['corrupt'] for e in es)} graded eval drafts "
          f"({sum(e['v1_code_ok'] is True for e in es)} passed the v1 code check, {sum(e['v1_code_ok'] is False for e in es)} failed it) "
          f"+ {sum(e['corrupt'] for e in es)} corrupted; {n} calls on {SMALL} (REAL Groq), effort {pol.check_effort}, "
          f"prompt v2, passages = the v2 pieces")
    print(f"  passages not found in v2 (fell back to the stored text): {sum(e['missing_v2'] for e in es)}; "
          f"drafts whose passages include a table piece (prefix): {sum(any(getattr(h.chunk, 'prefix', None) for h in e['hits']) for e in es)}")
    print(f"  grades: {', '.join(f'{g} {sum(e['grade'] == g for e in es)}' for g in sorted({e['grade'] for e in es}))}")
    print(f"  est tokens: ~{tin} in + ~{n * CHECK_OUT} out (in per call p50 ~{sorted(e['est_in'] for e in es)[n // 2]}); "
          f"1 call / {a.gap:.0f} s (~{n * a.gap / 60:.0f} min)")
    print(f"  {SMALL}: last 24 h {u[SMALL]['tokens']} tok -> after ~{u[SMALL]['tokens'] + tin + n * CHECK_OUT} of ceiling {CEILING}; "
          f"run cap {n + 2}; no 120b calls")
    for e in es:
        print(f"    {e['tag']:22s} grade {e['grade']:18s} v1 code {str(e['v1_code_ok']):5s} v1 model {str(e['v1_model_ok']):5s} "
              f"in ~{e['est_in']}")
    if not a.go:
        print("  (plan only; nothing sent.)")
        return
    from probe.probe_groq import KEY
    pl.api_key = KEY
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    pl.budget = Budget(f"replay_v2_checks_{stamp}", n + 2)
    res = []
    for i, e in enumerate(es):
        ctx = Ctx(rid=f"v2check-{i}", question=e["question"], t0=time.perf_counter(), cancel=threading.Event(), deadline_ms=60_000)
        ok, why = pl._model_check(ctx, e["draft"], e["hits"])
        end = next((x for x in ctx.events if x["ev"] == "call_end"), {})
        nums = next((x["numbers"] for x in ctx.events if x["ev"] == "check_numbers"), None)
        r = {k: e[k] for k in ("tag", "grade", "corrupt", "v1_code_ok", "v1_model_ok", "code_ok", "code_why")}
        r.update(v2_model_ok=ok, v2_why=why, numbers=nums, tokens_in=end.get("tokens_in"), tokens_out=end.get("tokens_out"),
                 work_ms=end.get("work_ms"))
        res.append(r)
        print(f"  {e['tag']:22s} {e['grade']:18s} v2 model {'PASS' if ok else 'REJECT'}  {why[:90]}", flush=True)
        if i + 1 < n:
            time.sleep(a.gap)
    out = ROOT / f"raw/replay_v2_checks_{stamp}.json"
    out.write_text(json.dumps({"label": POST_HOC, "results": res}, indent=2, ensure_ascii=False))

    def cnt(rs, g, ok):
        """How many entries with this grade got this verdict."""
        return sum(r["grade"].startswith(g) and r["v2_model_ok"] is ok for r in rs)
    prod = [r for r in res if r["v1_code_ok"] is True]
    nw, nc = sum(r["grade"] == "wrong" for r in prod), sum(r["grade"] == "correct" for r in prod)
    cr = [r for r in res if r["corrupt"]]
    rest = [r for r in res if not r["corrupt"] and r["v1_code_ok"] is False]
    print(f"\n[report] {POST_HOC}")
    print(f"  K's three numbers (the drafts production's model check would see = the 27 that passed the code check):")
    print(f"    wrong drafts caught:            {cnt(prod, 'wrong', False)} of {nw}   (v1 check: 0 of {nw})")
    print(f"    correct drafts falsely rejected: {cnt(prod, 'correct', False)} of {nc}   (v1 check: 0 of {nc})")
    print(f"    corrupted drafts rejected:       {sum(not r['v2_model_ok'] for r in cr)} of {len(cr)}")
    print(f"  extra, the {len(rest)} drafts the code check had already rejected: wrong rejected "
          f"{cnt(rest, 'wrong', False)} of {sum(r['grade'] == 'wrong' for r in rest)}, correct rejected "
          f"{cnt(rest, 'correct', False)} of {sum(r['grade'] == 'correct' for r in rest)}")
    print(f"-> {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
