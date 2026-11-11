"""§8 comparison (K, 2026-11-11 §46): for every draft of the eval, the code-check verdict vs the model-check
verdict vs K's hand grade. No Groq; run AFTER eval/apply_grades.py --write.

  .venv/bin/python eval/check_vs_grade.py eval_day1_20261111_124523   -> stdout + raw/check_vs_grade_<run>.md

Per draft (drafter "not in papers" drafts are skipped: no check ran on them):
  code_ok, model_ok (None = model check not run because the code check failed), sent?, and its grade:
  - a SENT draft takes the row's grade (answer_grade: correct / wrong);
  - a REJECTED draft takes K's optional "draft N grade:" from the blinded file (raw/grades_<run>.json); blank = unknown.
Code-only simulation (check_mode "code_only", §8 option ii), exact because the code check is deterministic:
  round 0 passes the code check -> code-only sends round 0;
  round 0 fails the code check  -> the real redraft got the code check's feedback, which is what code-only
                                    would have sent too, so code-only sends round 1 if it passes the code check;
  neither passes                -> the same `unverified` reply as the real run.
Answers to K's two questions:
  (1) wrong answers code-only would have let through = code-only-sent drafts graded wrong
      (vs wrong answers the real code + model check let through);
  (2) correct drafts the code check rejected = code_ok False drafts graded correct (needs K's draft grades).
Unknown grades are counted as unknown, never guessed.
"""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from relay.config import SETTINGS  # noqa: E402


def main():
    """Code-only vs code + model check against K's grades (what each check let through)."""
    run = sys.argv[1]
    meta = json.loads((ROOT / f"raw/meta_{run}.json").read_text())
    name_of = {SETTINGS[n].name: n for n in meta["settings"]}
    rows = {(r["request_id"], name_of[r["retrieval_setting"]]): r
            for r in csv.DictReader(open(ROOT / f"raw/results_{run}.csv"))}
    gp = ROOT / f"raw/grades_{run}.json"
    notes = json.loads(gp.read_text()) if gp.exists() else {}
    if not any(r["answer_grade"] for r in rows.values()):
        raise SystemExit("no grades in the results csv yet: run eval/apply_grades.py --write first")
    lines = ["| question x setting | round | code check | model check | sent | grade of this draft | code-only sends it |",
             "|---|---|---|---|---|---|---|"]
    C = Counter()
    for nm in meta["settings"]:
        for ln in open(ROOT / f"raw/events_{run}_{nm}.jsonl"):
            d = json.loads(ln)
            qid = d["row"]["request_id"]
            row = rows[(qid, nm)]
            tag = f"{qid} x {nm}"
            drafts = {e["round"]: e for e in d["events"] if e["ev"] == "draft_out"}
            checks = {e["round"]: e for e in d["events"] if e["ev"] == "check"}
            sent = next((r for r, c in checks.items() if c.get("ok")), None) if row["reply_kind"] == "answer" else None
            # code-only: first draft that passes the code check, valid while the path matches the real one
            co = None
            if 0 in checks and checks[0].get("code_ok"):
                co = 0
            elif 0 in checks and 1 in checks and checks[1].get("code_ok"):
                co = 1
            for rnd, dr in sorted(drafts.items()):
                if dr["draft"].get("not_in_papers") or rnd not in checks:
                    continue
                c = checks[rnd]
                if rnd == sent:
                    g = row["answer_grade"] or "ungraded"
                else:
                    g = (notes.get(tag, {}).get("drafts", {}).get(str(rnd), {}).get("label")) or "unknown"
                C["drafts"] += 1
                C[f"code_{'ok' if c.get('code_ok') else 'fail'}"] += 1
                if c.get("code_ok"):
                    C[f"model_{'ok' if c.get('model_ok') else 'fail'}"] += 1
                    if not c.get("model_ok"):
                        C[f"model_rejected_{g}"] += 1
                else:
                    C[f"code_rejected_{g}"] += 1
                if rnd == co:
                    C[f"codeonly_sent_{g}"] += 1
                if rnd == sent:
                    C[f"both_sent_{g}"] += 1
                mo = "not run" if c.get("model_ok") is None else ("OK" if c["model_ok"] else "FAIL")
                lines.append(f"| {tag} | {rnd} | {'OK' if c.get('code_ok') else 'FAIL'} | {mo} | "
                             f"{'yes' if rnd == sent else 'no'} | {g} | {'yes' if rnd == co else 'no'} |")
    summ = [
        f"Drafts with a check: {C['drafts']} (code OK {C['code_ok']}, code FAIL {C['code_fail']}; of the code-OK ones, "
        f"model OK {C['model_ok']}, model FAIL {C['model_fail']}).",
        f"(1) Wrong answers let through: code + model (real run) {C['both_sent_wrong']}; code-only would have sent "
        f"{C['codeonly_sent_wrong']} wrong, {C['codeonly_sent_correct']} correct, {C['codeonly_sent_unknown']} ungraded "
        f"(rejected drafts K did not grade).",
        f"    Model check rejections: {C['model_rejected_wrong']} graded wrong (caught), {C['model_rejected_correct']} "
        f"graded correct (false rejections), {C['model_rejected_unknown']} ungraded.",
        f"(2) Correct drafts the code check rejected: {C['code_rejected_correct']} (of {C['code_fail']} code rejections; "
        f"{C['code_rejected_wrong']} graded wrong, {C['code_rejected_unknown']} ungraded).",
    ]
    txt = "\n".join([f"# Code check vs model check vs K's grade, {run}", ""] + summ + [""] + lines)
    print(txt)
    (ROOT / f"raw/check_vs_grade_{run}.md").write_text(txt + "\n")


if __name__ == "__main__":
    main()
