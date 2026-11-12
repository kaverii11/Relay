"""After grading (K, 2026-11-11 §50). No Groq.

  .venv/bin/python eval/eval_breakdown.py eval_day1_20261111_124523   -> stdout + raw/eval_breakdown_<run>.md

1. Per-question breakdown across the three settings, from results.csv (answer_grade, reply_kind), with the
   question's answerability from eval/k_questions.csv; "changed" = the grade differs between settings.
2. §8 per draft: model-check verdict vs K's grade, and every code-check rejection with its cause. NOTE: check
   verdicts are not results.csv columns; they come from the run's event logs, and rejected-draft grades from
   raw/grades_<run>.json. Cause of a code-check rejection, decided mechanically from the quote:
     length    : the quote is in the passage but keeps < MIN_QUOTE_KEY letters/digits;
     splice    : the quote contains "..." / "…" (joins two places);
     not found : neither (a reformatted quote, or text from somewhere else).
"""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from relay.config import SETTINGS  # noqa: E402
from relay.prompts import claim_quotes  # noqa: E402
from relay.textnorm import MIN_QUOTE_KEY, match_key  # noqa: E402
from analysis.tables import base_id  # noqa: E402

SHORT = {"medium_rerank": "250/6 re-rank", "medium_norerank": "250/6 no re-rank", "medium_k3_norerank": "250/3 no re-rank"}
G = {"correct": "correct", "wrong": "WRONG", "refused_correctly": "ref. ok", "refused_wrongly": "REF. WRONG"}


def main():
    """Per question x setting: reply, grade, and why each check passed or failed."""
    run = sys.argv[1]
    meta = json.loads((ROOT / f"raw/meta_{run}.json").read_text())
    names = meta["settings"]
    name_of = {SETTINGS[n].name: n for n in names}
    qs = {q["id"]: q for q in csv.DictReader(open(ROOT / "eval/k_questions.csv"))}
    rows = [r for r in csv.DictReader(open(ROOT / "results.csv")) if r["scenario"] == "eval"]
    key = json.loads((ROOT / f"raw/blind_key_{run}.json").read_text())["key"]
    bid = {(v["question"], v["setting"]): b for b, v in key.items()}
    notes = json.loads((ROOT / f"raw/grades_{run}.json").read_text())
    cell = {(base_id(r["request_id"]), name_of[r["retrieval_setting"]]): r for r in rows}
    L = [f"# Eval breakdown, {run} (results.csv + event logs + K's grades)", "",
         "## Per question across the three settings", "",
         "| question | type | answerable | " + " | ".join(SHORT[n] for n in names) + " | changed with setting |",
         "|---|---|---|" + "---|" * len(names) + "---|"]
    changed = 0
    for qid in meta["order"]:
        gs = [cell[(qid, n)]["answer_grade"] for n in names]
        ch = len(set(gs)) > 1
        changed += ch
        L.append(f"| {qid} | {qs[qid]['type']} | {qs[qid]['answerable']} | "
                 + " | ".join(f"{G[cell[(qid, n)]['answer_grade']]} ({cell[(qid, n)]['reply_kind']}, {bid[(qid, n)]})"
                              for n in names) + f" | {'**yes**' if ch else 'no'} |")
    L += ["", f"Questions whose grade changed with the setting: {changed} of {len(meta['order'])}.", ""]

    # §8 per draft
    mc, cr = Counter(), []
    for n in names:
        for ln in open(ROOT / f"raw/events_{run}_{n}.jsonl"):
            d = json.loads(ln)
            qid = d["row"]["request_id"]
            r = cell[(qid, n)]
            ps = d["result"].get("passages") or []
            checks = {e["round"]: e for e in d["events"] if e["ev"] == "check"}
            sent = next((k for k, c in checks.items() if c.get("ok")), None) if r["reply_kind"] == "answer" else None
            for e in d["events"]:
                if e["ev"] != "draft_out" or e["round"] not in checks:
                    continue
                c, rnd = checks[e["round"]], e["round"]
                g = r["answer_grade"] if rnd == sent else \
                    notes.get(f"{qid} x {n}", {}).get("drafts", {}).get(str(rnd), {}).get("label", "ungraded")
                if c.get("code_ok"):
                    mc[("passed" if c.get("model_ok") else "rejected", g)] += 1
                    continue
                cause, bad = "not found", ""
                for cl in e["draft"].get("claims") or []:
                    cid = str(cl.get("chunk", ""))
                    t = ps[int(cid[1:]) - 1]["text"] if cid[1:].isdigit() and 1 <= int(cid[1:]) <= len(ps) else ""
                    for q in claim_quotes(cl):
                        k = match_key(q)
                        if len(k) >= MIN_QUOTE_KEY and k in match_key(t):
                            continue
                        bad = q
                        cause = ("length" if k in match_key(t) else
                                 "splice" if ("..." in q or "…" in q) else "not found")
                        break
                    if bad:
                        break
                note = notes.get(f"{qid} x {n}", {}).get("drafts", {}).get(str(rnd), {}).get("note", "")
                cr.append((bid[(qid, n)], rnd, g, cause, bad[:70], note))
    L += ["## §8: model check vs K's grade (drafts that passed the code check)", "",
          "| model check | graded correct | graded wrong |", "|---|---|---|"]
    for v in ("passed", "rejected"):
        L.append(f"| {v} | {mc[(v, 'correct')]} | {mc[(v, 'wrong')]} |")
    L += ["", "## §8: every code-check rejection", "",
          "| entry | draft | K's grade of the draft | cause | failing quote | K's note |", "|---|---|---|---|---|---|"]
    for b, rnd, g, cause, q, note in sorted(cr):
        L.append(f"| {b} | {rnd} | {g} | {cause} | {q!r} | {note} |")
    cc = Counter((g, cause) for _, _, g, cause, _, _ in cr)
    L += ["", "Code-check rejections by grade and cause: " + ", ".join(f"{g} / {c}: {k}" for (g, c), k in sorted(cc.items()))]
    txt = "\n".join(L)
    print(txt)
    (ROOT / f"raw/eval_breakdown_{run}.md").write_text(txt + "\n")


if __name__ == "__main__":
    main()
