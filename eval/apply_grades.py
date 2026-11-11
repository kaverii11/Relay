"""Copy K's hand grades into the eval run's results csv (answer_grade column). No Groq.

  .venv/bin/python eval/apply_grades.py raw/blind_reading_eval_day1_<stamp>.md          # check only
  .venv/bin/python eval/apply_grades.py raw/blind_reading_eval_day1_<stamp>.md --write  # fill the csv

Blinded file (K §46, the one to grade): entries B01..B60 are joined back to (question, setting) through
raw/blind_key_<run>.json. The open file raw/reading_<run>.md ("## Q57 x medium_rerank" headers) also works.
Labels: the DECISIONS §6 rubric only: correct | wrong | refused_correctly | refused_wrongly (unverified on an
answerable question = refused_wrongly, on an unanswerable one = refused_correctly; K applies it by hand).
Anything after the label on the same line is kept as a note in raw/grades_<run>.json, not in the csv.
Optional "draft N grade:" lines (rejected drafts only) go to the same json for eval/check_vs_grade.py.
Nothing is guessed: a blank stays blank, and --write refuses while any label is invalid.
"""
from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from relay.config import SETTINGS  # noqa: E402
from relay.service import COLUMNS  # noqa: E402

LABELS = ("correct", "wrong", "refused_correctly", "refused_wrongly")


def parse(md: Path, key: dict | None):
    """-> {(qid, setting): {"grade": str, "drafts": {n: str}}}"""
    out, cur = {}, None
    for line in md.read_text().splitlines():
        m = re.match(r"## (Q\d+) x (\S+)$", line) or re.match(r"## (B\d+)$", line)
        if m:
            if m.group(0).startswith("## B"):
                k = key[m.group(1)]
                cur = (k["question"], k["setting"])
            else:
                cur = (m.group(1), m.group(2))
            out[cur] = {"grade": "", "drafts": {}}
            continue
        if cur is None:
            continue
        m = re.match(r"draft (\d+) grade:\s*(.*)$", line)
        if m:
            if m.group(2).strip():
                out[cur]["drafts"][int(m.group(1))] = m.group(2).strip()
            continue
        m = re.match(r"grade:\s*(.*)$", line)
        if m:
            out[cur]["grade"] = m.group(1).strip()
    return out


def label_of(g):
    """The grade word at the start of a grade line ('correct', 'wrong', ...)."""
    return re.split(r"[\s,;:]|\s-\s", g, maxsplit=1)[0].lower()


def main():
    """Join K's grades back to rows through the blind key; --write puts them in the results file."""
    md = Path(sys.argv[1])
    write = "--write" in sys.argv
    blind = md.name.startswith("blind_reading_")
    run = md.stem[len("blind_reading_" if blind else "reading_"):]
    key = json.loads((ROOT / f"raw/blind_key_{run}.json").read_text())["key"] if blind else None
    meta = json.loads((ROOT / f"raw/meta_{run}.json").read_text())
    name_of = {SETTINGS[n].name: n for n in meta["settings"]}
    csv_p = ROOT / f"raw/results_{run}.csv"
    rows = list(csv.DictReader(open(csv_p)))
    grades = parse(md, key)
    bid_of = {(v["question"], v["setting"]): b for b, v in (key or {}).items()}
    missing, bad, notes, graded = [], [], {}, 0
    for r in rows:
        k = (r["request_id"], name_of[r["retrieval_setting"]])
        g = grades.get(k, {"grade": "", "drafts": {}})
        tag = f"{k[0]} x {k[1]}"
        shown = bid_of[k] if blind else tag           # blind mode never prints a setting name
        for n, dg in g["drafts"].items():
            if label_of(dg) not in LABELS:
                bad.append(f"{shown} draft {n}: {dg!r}")
        if not g["grade"]:
            missing.append(tag)
        elif label_of(g["grade"]) not in LABELS:
            bad.append(f"{shown}: {g['grade']!r}")
        else:
            r["answer_grade"] = label_of(g["grade"])
            graded += 1
        if g["grade"] or g["drafts"]:
            notes[tag] = {"grade": g["grade"], "label": label_of(g["grade"]) if g["grade"] else "",
                          "drafts": {str(n): {"note": dg, "label": label_of(dg)} for n, dg in g["drafts"].items()}}
    n_dr = sum(len(v["drafts"]) for v in notes.values())
    print(f"{len(rows)} rows; graded {graded}; "
          f"blank {len(missing)}; invalid {len(bad)}; rejected-draft grades {n_dr}")
    for b in bad:
        print("  invalid:", b)
    if missing and not blind:
        print("  blank:", ", ".join(missing[:12]) + (" ..." if len(missing) > 12 else ""))
    elif missing:
        print(f"  {len(missing)} blank (names hidden in blind mode)")
    if not write:
        return
    if bad:
        raise SystemExit("not written: fix the invalid labels first (allowed: " + ", ".join(LABELS) + ")")
    with open(csv_p, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in COLUMNS})
    (ROOT / f"raw/grades_{run}.json").write_text(json.dumps(notes, indent=2))
    print(f"-> {csv_p.relative_to(ROOT)} answer_grade filled; notes raw/grades_{run}.json. Then re-run "
          f"scripts/assemble_results.py, analysis/tables.py (Table 3) and eval/check_vs_grade.py (§8).")


if __name__ == "__main__":
    main()
