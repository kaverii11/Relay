"""Check K's question file against its format AND against the papers. No Groq calls.

  .venv/bin/python eval/check_questions.py                  # eval/k_questions.csv
  .venv/bin/python eval/check_questions.py path/to/file.csv

Columns (K, 2026-11-10):
  id, set, type, question, answerable, gate_expected, expected_answer, must_include, paper, section, page, searched_terms
  set            BLANK until eval/split.py assigns eval | tuning (K: seeded split, never by hand)
  type           one of K's eight question types (TYPES below; empty = not enforced yet)
  answerable     yes | no
  gate_expected  pass | refuse (K): refuse ONLY when the papers don't touch the question at all.
                 False premise / comparison not made / number not reported = answerable no, gate pass.
                 The cutoff is tuned on this column, not on answerable.
  expected_answer, must_include, paper, page   required when answerable = yes
  must_include   the fact(s) a correct answer needs (a number with its unit, or a mechanism's name);
                 several facts: separate with ";" (each is checked on its own)
  paper          arXiv id, with or without version or ".pdf" (1706.03762, 1706.03762v7, 2410.00037v1.pdf)
  section        as in the paper, e.g. "3.2.2", "3.2.1 Architecture", "Appendix D" (recommended)
  page           PDF page number, or a range 4-5
  searched_terms required when answerable = no (may be filled for any row); separate terms with ";"
Use a spreadsheet or quote fields that contain commas.

What it checks against the papers (papers/*.pdf, the pinned versions):
  - must_include appears on the cited page(s), after the same normalisation the citation check
    uses (relay.textnorm.match_key: case, spacing, punctuation, hyphenated line breaks). If not,
    it lists the pages where it does appear, so a wrong page number is easy to fix.
  - section exists in that paper's table of contents (as numbered by relay/ingest.py).
  - each searched term of an unanswerable question: where it appears in any of the three papers.
    This doesn't decide "the papers don't say"; it shows K where to look again.
Errors (exit 1) = format problems. Warnings = things to look at; K decides.
"""
from __future__ import annotations

import csv
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pymupdf as fitz  # noqa: E402

from relay.config import PAPER_VERSIONS  # noqa: E402
from relay.ingest import load  # noqa: E402
from relay.textnorm import match_key  # noqa: E402

COLUMNS = ["id", "set", "type", "question", "answerable", "gate_expected", "expected_answer", "must_include",
           "paper", "section", "page", "searched_terms"]
TYPES: list[str] = []      # K's eight types; fill in to reject typos (empty = report counts only)
MIN_KEY = 4                # shorter normalised strings (e.g. "0.1" -> "01") match almost anywhere


def pages_text():
    out = {}
    for v in PAPER_VERSIONS:
        doc = fitz.open(ROOT / f"papers/{v}.pdf")
        out[v] = [match_key(p.get_text()) for p in doc]
    return out


def resolve_paper(s):
    s = s.strip().removesuffix(".pdf")
    hits = [v for v in PAPER_VERSIONS if v == s or v.split("v")[0] == s]
    return hits[0] if hits else None


def section_number(s):
    """'3.2.1 Architecture' -> '3.2.1'; 'Appendix D' / 'Appendix D.2' -> 'D' / 'D.2'; '§5.8' -> '5.8'."""
    s = s.strip().lstrip("§").strip()
    m = re.match(r"(?i)appendix\s+([A-Z](?:\.\d+)*)", s)
    return m.group(1) if m else s.split(" ")[0]


def parse_pages(s):
    m = re.fullmatch(r"\s*(\d+)\s*(?:[-–]\s*(\d+))?\s*", s or "")
    if not m:
        return None
    a = int(m.group(1))
    b = int(m.group(2) or a)
    return list(range(a, b + 1)) if b >= a else None


def check_facts(r, v, pg, txt, W):
    """must_include may hold several facts separated by ';'. Each is looked for on the cited page(s)."""
    facts = [x.strip() for x in r["must_include"].split(";") if x.strip()]
    for mi in facts:
        k = match_key(mi)
        if len(k) < MIN_KEY:
            W(f"must_include {mi!r} is too short to check against the page; check by hand")
        elif not any(k in txt[v][p - 1] for p in pg):
            found = [i + 1 for i, t_ in enumerate(txt[v]) if k in t_]
            W(f"must_include {mi!r} not found verbatim on p.{r['page']} of {v}"
              + (f"; it appears on p.{', p.'.join(map(str, found))}" if found
                 else "; not anywhere in that paper (paraphrase, derived number, or a format like 1e-4 vs 10^-4?)"))
    ea = match_key(r["expected_answer"])
    if facts and ea and any(match_key(f) not in ea for f in facts):
        W("not every must_include fact is in expected_answer")


def main(path: Path):
    rows = list(csv.DictReader(open(path, newline="", encoding="utf-8-sig")))
    errs, warns = [], []
    cols = list(rows[0].keys()) if rows else []
    missing = [c for c in COLUMNS if c not in cols]
    if missing:
        sys.exit(f"{path}: missing columns {missing}. Expected: {','.join(COLUMNS)}")
    extra = [c for c in cols if c not in COLUMNS]
    if extra:
        warns.append(f"extra columns kept but not used: {extra}")

    txt = pages_text()
    sections = {}
    for c in load(ROOT / "data/chunks_w250.jsonl"):
        sections.setdefault(c.paper, set()).add(c.section.split(" ")[0])

    ids, qs = Counter(r["id"].strip() for r in rows), Counter(match_key(r["question"]) for r in rows)
    for r in rows:
        rid = r["id"].strip() or "(no id)"
        E = lambda m: errs.append(f"{rid}: {m}")    # noqa: E731
        W = lambda m: warns.append(f"{rid}: {m}")   # noqa: E731
        if ids[r["id"].strip()] > 1:
            E("duplicate id")
        if qs[match_key(r["question"])] > 1:
            E("duplicate question (same text after normalisation)")
        if not r["question"].strip():
            E("empty question")
        if r["set"].strip() not in ("", "eval", "tuning"):
            E(f"set must be blank (before the split), eval or tuning, got {r['set']!r}")
        t = r["type"].strip()
        if not t:
            E("type is empty")
        elif TYPES and t not in TYPES:
            E(f"type {t!r} not one of {TYPES}")
        ans = r["answerable"].strip().lower()
        if ans not in ("yes", "no"):
            E(f"answerable must be yes or no, got {r['answerable']!r}")
            continue
        ge = r["gate_expected"].strip().lower()
        if ge not in ("pass", "refuse"):
            E(f"gate_expected must be pass or refuse, got {r['gate_expected']!r}")
        elif ans == "yes" and ge == "refuse":
            E("answerable=yes but gate_expected=refuse")
        elif ans == "no" and ge == "pass" and not (r["paper"].strip() and r["page"].strip()):
            W("gate_expected=pass on an unanswerable question: give paper + page of the passage the gate should find")

        if ans == "yes":
            for c in ("expected_answer", "must_include", "paper", "page"):
                if not r[c].strip():
                    E(f"answerable=yes needs {c}")
            v = resolve_paper(r["paper"]) if r["paper"].strip() else None
            if r["paper"].strip() and not v:
                E(f"paper {r['paper']!r} is not one of {PAPER_VERSIONS}")
                continue
            pg = parse_pages(r["page"]) if r["page"].strip() else None
            if r["page"].strip() and not pg:
                E(f"page {r['page']!r} is not a number or a range like 4-5")
            if v and pg and max(pg) > len(txt[v]):
                E(f"page {r['page']} is past the end of {v} ({len(txt[v])} pages)")
                pg = None
            if v and r["section"].strip():
                sec = section_number(r["section"])
                if sec not in sections.get(v, set()):
                    W(f"section {sec} not found in {v}'s table of contents "
                      f"(has e.g. {sorted(sections.get(v, set()))[:8]}...)")
            elif v:
                W("section is empty (recommended)")
            if v and pg:
                check_facts(r, v, pg, txt, W)
        else:
            terms = [x.strip() for x in r["searched_terms"].split(";") if x.strip()]
            if not terms:
                E("answerable=no needs searched_terms (what you searched the PDFs for)")
            for term in terms:
                k = match_key(term)
                if len(k) < MIN_KEY:
                    W(f"searched term {term!r} is too short to look up")
                    continue
                where = [f"{v} p.{i + 1}" for v in PAPER_VERSIONS for i, t_ in enumerate(txt[v]) if k in t_]
                if where:
                    W(f"searched term {term!r} DOES appear: {', '.join(where[:8])}"
                      + (f" (+{len(where) - 8} more)" if len(where) > 8 else "") + ". Re-read those pages.")
            if r["paper"].strip() and r["page"].strip():          # K points to the nearest passage: check it too
                v = resolve_paper(r["paper"])
                pg = parse_pages(r["page"])
                if v and pg and max(pg) <= len(txt[v]):
                    check_facts(r, v, pg, txt, W)

    print(f"{path}: {len(rows)} questions")
    by = Counter((r["set"].strip() or "(blank)", r["answerable"].strip().lower(), r["gate_expected"].strip().lower())
                 for r in rows)
    for (s, a, g), n in sorted(by.items()):
        print(f"  set={s:8s} answerable={a:3s} gate_expected={g:6s} {n}")
    if any(not r["set"].strip() for r in rows):
        print("  set is blank: run eval/split.py once all questions are written (K). No cutoff tuning until then.")
    print("  by type: " + ", ".join(f"{t} {n}" for t, n in sorted(Counter(r['type'].strip() for r in rows).items())))
    for m in errs:
        print("ERROR  ", m)
    for m in warns:
        print("warning", m)
    print(f"{len(errs)} error(s), {len(warns)} warning(s)")
    sys.exit(1 if errs else 0)


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "eval/k_questions.csv")
