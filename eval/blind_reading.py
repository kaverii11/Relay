"""Blinded reading file for hand grading (K, 2026-11-11 §46). No Groq.

  .venv/bin/python eval/blind_reading.py eval_day1_20261111_124523 [--seed 7]
    -> raw/blind_reading_<run>.md   (what K grades: entries B01..B60, shuffled, no setting names)
    -> raw/blind_key_<run>.json     (B## -> question id + setting; K does not open it until grading is done)

Built from the run's event logs, not from the open reading file. Each entry keeps only what grading needs:
the question, the reply kind, every draft with its claims and quotes, both check verdicts, the final reply
and its citations, and the passages' text with their section cites.
Removed because they identify the setting: setting name, timings, call and token counts, cached tokens,
gate scores and which query won, degrade level, BM25 / cross-encoder scores (their order would show the
re-rank). Left in, unavoidably: the NUMBER of passages (3 vs 6) shows k, so 250/3 entries are recognisable;
the two 250/6 settings are not told apart by anything left in the entry.
Every entry ends with "grade:" (the final reply, §6 rubric labels). Drafts that were NOT sent (rejected by a
check) carry an optional "draft N grade:" line, used only for the §8 code-only vs both comparison
(eval/check_vs_grade.py); leave them blank if you don't want that count.
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def load_run(run):
    meta = json.loads((ROOT / f"raw/meta_{run}.json").read_text())
    recs = []
    for nm in meta["settings"]:
        for line in open(ROOT / f"raw/events_{run}_{nm}.jsonl"):
            d = json.loads(line)
            recs.append((d["row"]["request_id"], nm, d))
    return meta, recs


def block(bid, qid, d, question):
    res, ev = d["result"], d["events"]
    checks = {c["round"]: c for c in ev if c["ev"] == "check"}
    drafts = [e for e in ev if e["ev"] == "draft_out"]
    sent_round = max((c["round"] for c in checks.values() if c.get("ok")), default=None)
    L = [f"## {bid}", f"**Q:** {question}", "", f"- reply: **{d['row']['reply_kind']}**", ""]
    for i, dr in enumerate(drafts):
        dd, c = dr["draft"], checks.get(dr["round"], {})
        L.append(f"**Draft {i}:** {dd.get('answer', '')}")
        if dd.get("not_in_papers"):
            L.append("  - drafter said: not in papers")
        for cl in dd.get("claims", []) or []:
            qs = cl.get("quotes") if cl.get("quotes") is not None else [cl.get("quote", "")]
            L.append(f"  - {cl.get('chunk')}: " + " | ".join(f"\"{q}\"" for q in (qs if isinstance(qs, list) else [qs])))
        if c:
            L.append(f"  - code check: {'OK' if c.get('code_ok') else 'FAIL'}" + (f" ({c['code_why']})" if c.get("code_why") else ""))
            L.append("  - model check: " + ("not run" if c.get("model_ok") is None else
                                            ("OK" if c["model_ok"] else f"FAIL ({c.get('model_why')})")))
            if dr["round"] != sent_round and not dd.get("not_in_papers"):
                L.append(f"draft {i} grade: ")
        L.append("")
    L.append(f"**Final reply:** {res.get('answer', '')}")
    L.append(f"citations: {res.get('citations')}")
    L += ["", "**Passages the drafter saw:**"]
    for i, ps in enumerate(res.get("passages") or [], 1):
        L.append(f"- C{i} {ps['cite']}: {ps['text']}")
    L += ["", "grade: ", ""]
    return "\n".join(L)


def main():
    run = sys.argv[1]
    seed = int(sys.argv[sys.argv.index("--seed") + 1]) if "--seed" in sys.argv else 7
    out_md, out_key = ROOT / f"raw/blind_reading_{run}.md", ROOT / f"raw/blind_key_{run}.json"
    if out_md.exists() and "--overwrite" not in sys.argv:
        raise SystemExit(f"{out_md.name} exists (may hold grades); --overwrite to rebuild")
    meta, recs = load_run(run)
    recs.sort(key=lambda r: (r[0], r[1]))
    random.Random(seed).shuffle(recs)
    key, parts = {}, [f"# Blinded reading file ({len(recs)} entries, shuffled with seed {seed})", "",
                      "Labels (DECISIONS §6): correct | wrong | refused_correctly | refused_wrongly. "
                      "`unverified` on an answerable question = refused_wrongly; on an unanswerable one = refused_correctly.",
                      "Anything after the label on the same line is kept as a note.", ""]
    for i, (qid, nm, d) in enumerate(recs, 1):
        bid = f"B{i:02d}"
        key[bid] = {"question": qid, "setting": nm}
        parts.append(block(bid, qid, d, d["question"]))
    out_md.write_text("\n".join(parts) + "\n")
    out_key.write_text(json.dumps({"run": run, "seed": seed, "key": key}, indent=2))
    print(f"-> {out_md.relative_to(ROOT)} ({len(recs)} entries); key -> {out_key.relative_to(ROOT)} (don't open before grading)")


if __name__ == "__main__":
    main()
