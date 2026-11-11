"""K (2026-11-11 §56 item 4): every number in the write-up's PROSE and in Table 1 must appear in results.csv,
probe/FINDINGS.md or DECISIONS.md. Lists the ones that don't. Never edits anything.

  .venv/bin/python scripts/check_numbers.py

Numbers: digit runs with an optional decimal part ("3.867", "1,237" -> 1237, "35.0 %" -> 35.0). Skipped as
identifiers, not measurements: section refs (§43), question / entry / table ids (Q36, B05, T4, "Table 3"),
model and paper names (20b, 120b, gpt-oss, 1706.03762v7), version tags (v1, v2), dates, times of day, single
digits, and numbers inside `[GAP...]` / `[K...]` placeholders.
Match: the number as written, or the same value formatted plainly (1,237 / 1237; 35.0 / 35), as a whole token in a
source. A number that is only derived (e.g. a percentile computed from results.csv) is reported separately if
it appears in the tables computed from results.csv (raw/tables_20261111_final.md, raw/eval_breakdown_*.md).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

NUM = re.compile(r"(?<![\w.§/:-])(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)(?![\w])")
SKIP_BEFORE = re.compile(r"(§|Q|B|T|Table |Tables |v|sec |p\.|pp\.|~?Limit |\bn ?= ?)$")


def numbers(text):
    """Every number in a line of prose, skipping ids, dates, versions and placeholders."""
    text = re.sub(r"`\[(GAP|K)[^`]*`", " ", text)                  # placeholders
    text = re.sub(r"\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}:\d{2}(?::\d{2})?\b", " ", text)   # dates, clock times
    text = re.sub(r"\b(gpt-oss-)?(20|120)b\b|\b\d{4}\.\d{5}v\d\b", " ", text)        # model / paper ids
    out = []
    for m in NUM.finditer(text):
        tok = m.group(1)
        before = text[max(0, m.start() - 8):m.start()]
        if SKIP_BEFORE.search(before):
            continue
        v = tok.replace(",", "")
        if "." not in v and len(v) < 2:
            continue
        out.append((tok, text[max(0, m.start() - 40):m.end() + 25].replace("\n", " ")))
    return out


def forms(tok):
    """The ways a number may be written in a source (1,237 / 1237; 35.0 / 35)."""
    v = tok.replace(",", "")
    f = {tok, v}
    if "." in v:
        f.add(v.rstrip("0").rstrip("."))
    else:
        f.add(f"{int(v):,}")
    return {x for x in f if x}


def found_in(tok, text):
    """True if the number appears as a whole token in the text."""
    return any(re.search(rf"(?<![\d.]){re.escape(x)}(?![\d])", text) for x in forms(tok))


def main():
    """List write-up numbers with no source in results.csv, probe/FINDINGS.md or DECISIONS.md."""
    md = (ROOT / "writeup/writeup.md").read_text()
    prose = md[md.index("## 1. What I built and why"):md.index("## Results tables")]
    t1 = md[md.index("### Table 1"):md.index("### Table 2a")]
    srcs = {"results.csv": (ROOT / "results.csv").read_text(), "probe/FINDINGS.md": (ROOT / "probe/FINDINGS.md").read_text(),
            "DECISIONS.md": (ROOT / "DECISIONS.md").read_text()}
    derived = "\n".join(p.read_text() for p in [ROOT / "raw/tables_20261111_final.md", *sorted((ROOT / "raw").glob("eval_breakdown_*.md"))]
                        if p.exists())
    total, miss, only_derived = 0, [], []
    for part, text in (("prose", prose), ("Table 1", t1)):
        sec = "?"
        for line in text.splitlines():
            if line.startswith("## ") or line.startswith("### "):
                sec = line.lstrip("# ")[:40]
            for tok, ctx in numbers(line):
                total += 1
                if any(found_in(tok, s) for s in srcs.values()):
                    continue
                (only_derived if found_in(tok, derived) else miss).append((part, sec, tok, ctx))
    print(f"numbers checked: {total} (write-up prose + Table 1)")
    print(f"not in results.csv / probe/FINDINGS.md / DECISIONS.md: {len(miss) + len(only_derived)}")
    print(f"\n  of which found only in the tables computed from results.csv ({len(only_derived)}):")
    for part, sec, tok, ctx in only_derived:
        print(f"    [{part} | {sec}] {tok}   ...{ctx}...")
    print(f"\n  found nowhere ({len(miss)}):")
    for part, sec, tok, ctx in miss:
        print(f"    [{part} | {sec}] {tok}   ...{ctx}...")
    return 1 if miss else 0


if __name__ == "__main__":
    sys.exit(main())
