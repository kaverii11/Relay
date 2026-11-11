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
                 several facts: separate with ";" (each is checked on its own;
                 a piece starting with "not"/"no", e.g. "not reported", is a grading note and isn't looked up)
  paper          arXiv id, with or without version or ".pdf" (1706.03762, 1706.03762v7, 2410.00037v1.pdf)
  section        as in the paper, e.g. "3.2.2", "3.2.1 Architecture", "Appendix D" (recommended)
  page           PDF page number, or a range 4-5
  two papers     (cross-paper questions) separate paper, section and page with ";" in the same order:
                 paper "2410.00037v1; 2507.07955v2", section "5.1; Appendix F", page "22; 38".
                 Each must_include fact must appear on at least one of the cited pages.
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
    """Each paper's pages as match keys, to look facts up."""
    out = {}
    for v in PAPER_VERSIONS:
        doc = fitz.open(ROOT / f"papers/{v}.pdf")
        out[v] = [match_key(p.get_text()) for p in doc]
    return out


def resolve_paper(s):
    """A paper name or id as written in the question file -> its pinned version id."""
    s = s.strip().removesuffix(".pdf")
    hits = [v for v in PAPER_VERSIONS if v == s or v.split("v")[0] == s]
    return hits[0] if hits else None


def section_number(s):
    """'3.2.1 Architecture' -> '3.2.1'; 'Appendix D' / 'Appendix D.2' -> 'D' / 'D.2'; '§5.8' -> '5.8'."""
    s = s.strip().lstrip("§").strip()
    m = re.match(r"(?i)appendix\s+([A-Z](?:\.\d+)*)", s)
    return m.group(1) if m else s.split(" ")[0]


def parse_pages(s):
    """'7' or '11-12' -> the page range."""
    m = re.fullmatch(r"\s*(\d+)\s*(?:[-–]\s*(\d+))?\s*", s or "")
    if not m:
        return None
    a = int(m.group(1))
    b = int(m.group(2) or a)
    return list(range(a, b + 1)) if b >= a else None


def check_facts(r, cites, txt, W):
    """must_include may hold several facts separated by ';'. Each is looked for on the cited page(s).
    cites = [(paper_version, [pages]), ...]: one entry, or one per paper for a cross-paper question."""
    facts = [x.strip() for x in r["must_include"].split(";") if x.strip()]
    # "not reported", "no wall-clock comparison": grading notes about what's MISSING, not page facts
    facts = [x for x in facts if not re.match(r"(?i)(not|no)\b", x)]
    for mi in facts:
        k = match_key(mi)
        if len(k) < MIN_KEY:
            W(f"must_include {mi!r} is too short to check against the page; check by hand")
        elif not any(k in txt[v][p - 1] for v, pg in cites for p in pg):
            found = [f"{v} p.{i + 1}" for v, _ in cites for i, t_ in enumerate(txt[v]) if k in t_]
            W(f"must_include {mi!r} not found verbatim on p.{r['page']} of {'/'.join(v for v, _ in cites)}"
              + (f"; it appears on {', '.join(found)}" if found
                 else "; not anywhere in the cited paper(s) (paraphrase, derived number, or a format like 1e-4 vs 10^-4?)"))
    ea = match_key(r["expected_answer"])
    if facts and ea and any(match_key(f) not in ea for f in facts):
        W("not every must_include fact is in expected_answer")


def citations(r, txt, sections, E, W):
    """paper/section/page -> [(version, [pages])]. Several papers: ';'-separated, same order in all three.
    Returns None on a paper error (skip the row), [] if pages are missing or bad."""
    papers = [x.strip() for x in r["paper"].split(";")] if r["paper"].strip() else []
    pages = [x.strip() for x in r["page"].split(";")] if r["page"].strip() else []
    secs = [x.strip() for x in r["section"].split(";")] if r["section"].strip() else []
    if len(papers) > 1 and (len(pages) != len(papers) or (secs and len(secs) != len(papers))):
        E(f"{len(papers)} papers but {len(pages)} page entries and {len(secs)} section entries: "
          "give one of each per paper, ';'-separated, in the same order")
        return []
    out = []
    for i, ps in enumerate(papers):
        v = resolve_paper(ps)
        if not v:
            E(f"paper {ps!r} is not one of {PAPER_VERSIONS}")
            return None
        if i < len(secs) and secs[i]:
            sec = section_number(secs[i])
            if sec not in sections.get(v, set()):
                W(f"section {sec} not found in {v}'s table of contents "
                  f"(has e.g. {sorted(sections.get(v, set()))[:8]}...)")
        else:
            W(f"section is empty for {v} (recommended)")
        if i >= len(pages):
            continue
        pg = parse_pages(pages[i])
        if not pg:
            E(f"page {pages[i]!r} is not a number or a range like 4-5")
        elif max(pg) > len(txt[v]):
            E(f"page {pages[i]} is past the end of {v} ({len(txt[v])} pages)")
        else:
            out.append((v, pg))
    return out


def main(path: Path):
    """Check the question file: columns, values, and that each must_include fact is on the cited page."""
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
            cites = citations(r, txt, sections, E, W)
            if cites is None:
                continue
            if cites:
                check_facts(r, cites, txt, W)
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
                cites = citations(r, txt, sections, E, W)
                if cites:
                    check_facts(r, cites, txt, W)

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
