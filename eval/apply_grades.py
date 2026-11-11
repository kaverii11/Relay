"""Copy K's hand grades from an eval reading file into that run's results csv (answer_grade column). No Groq.

  .venv/bin/python eval/apply_grades.py raw/reading_eval_day1_<stamp>.md          # check: lists missing / bad
  .venv/bin/python eval/apply_grades.py raw/reading_eval_day1_<stamp>.md --write  # fill the csv

K writes one label on each block's "grade:" line. Labels are the DECISIONS §6 rubric only:
correct | wrong | refused_correctly | refused_wrongly. Anything after the label (e.g. "wrong - cites C2,
which does not say 0.1") is kept as a note in raw/grades_<run>.json, not in the csv. The rubric has no
rule for the `unverified` reply (K §44); K grades those rows with one of the four labels like any other.
Nothing is guessed: a block left blank stays blank, and --write refuses while any label is invalid.
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


def parse(md: Path):
    out, cur = {}, None
    for line in md.read_text().splitlines():
        m = re.match(r"## (Q\d+) x (\S+)$", line)
        if m:
            cur = (m.group(1), m.group(2))
            continue
        m = re.match(r"grade:\s*(.*)$", line)
        if m and cur:
            out[cur] = m.group(1).strip()
            cur = None
    return out


def main():
    md = Path(sys.argv[1])
    write = "--write" in sys.argv
    run = md.stem[len("reading_"):]
    csv_p = md.with_name(f"results_{run}.csv")
    rows = list(csv.DictReader(open(csv_p)))
    grades = parse(md)
    by_key = {}
    for r in rows:
        nm = next(n for n, s in SETTINGS.items() if s.name == r["retrieval_setting"] and n in json.loads(
            (md.with_name(f"meta_{run}.json")).read_text())["settings"])
        by_key[(r["request_id"], nm)] = r
    missing, bad, notes = [], [], {}
    for key, r in by_key.items():
        g = grades.get(key, "")
        if not g:
            missing.append(f"{key[0]} x {key[1]}")
            continue
        label = re.split(r"[\s,;:-]", g, maxsplit=1)[0].lower()
        if label not in LABELS:
            bad.append(f"{key[0]} x {key[1]}: {g!r}")
            continue
        r["answer_grade"] = label
        notes[f"{key[0]} x {key[1]}"] = g
    print(f"{len(by_key)} rows; graded {len(notes)}; blank {len(missing)}; invalid {len(bad)}")
    for b in bad:
        print("  invalid:", b)
    if missing:
        print("  blank:", ", ".join(missing[:12]) + (" ..." if len(missing) > 12 else ""))
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
    print(f"-> {csv_p.relative_to(ROOT)} answer_grade filled; notes raw/grades_{run}.json. "
          f"Then re-run scripts/assemble_results.py and analysis/tables.py for Table 3.")


if __name__ == "__main__":
    main()
