"""Turn the three PDFs into citable chunks.

Each chunk carries: paper id+version, section number+title (from the PDF's own
bookmarks), and page range, so an answer can cite e.g. [1706.03762v7 §3.2.2 p.4].

Figure-label noise (blocks of 1-2 character lines from vector figures) is dropped.
Chunks never cross a section boundary.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

import pymupdf

from relay.textnorm import corpus_vocab, dehyphenate

ROOT = Path(__file__).resolve().parents[1]
PAPERS = {
    "1706.03762v7": "Attention Is All You Need",
    "2410.00037v1": "Moshi: a speech-text foundation model for real-time dialogue",
    "2507.07955v2": "Dynamic Chunking for End-to-End Hierarchical Sequence Modeling",
}


@dataclass
class Chunk:
    id: str
    paper: str
    title: str
    section: str        # "3.2.2 Multi-Head Attention"
    page_start: int
    page_end: int
    text: str
    tables: list = None   # v2 (K §51): table numbers whose caption + header row were repeated at the start

    def cite(self) -> str:
        pg = f"p.{self.page_start}" if self.page_start == self.page_end else f"pp.{self.page_start}-{self.page_end}"
        return f"[{self.paper} §{self.section.split(' ')[0]} {pg}]"


def _numbered_toc(doc):
    """Give TOC entries numbers like 3.2.1 from their level. Appendix entries after
    'References'/'Appendix' get letters, which matches how these papers label them."""
    entries = []
    for lvl, title, page, dest in doc.get_toc(simple=False):
        # bookmark y is PDF space (origin bottom-left); blocks are top-left
        to = dest.get("to") if dest else None
        y = doc[page - 1].rect.height - to.y if to is not None else 0
        entries.append((lvl, title, page, y))
    # Some PDFs have no "References" bookmark: find the heading in the text instead,
    # otherwise the bibliography is silently filed under the last section (Conclusion).
    if not any(re.match(r"(?i)^(references|bibliography)", t.strip()) for _, t, _, _ in entries):
        for pno, page in enumerate(doc, start=1):
            for b in page.get_text("blocks"):
                if re.fullmatch(r"(?i)\s*(references|bibliography)\s*", b[4]):
                    entries.append((1, "References", pno, b[1] - 1))
        entries.sort(key=lambda e: (e[2], e[3]))
    counters = [0] * 8
    out, appendix = [], False
    for lvl, title, page, y in entries:
        t = title.strip()
        if re.match(r"(?i)^(references|bibliography|acknowledg)", t):
            out.append(("", t, page, y))
            if t.lower().startswith(("references", "bibliography")):
                appendix = True          # everything after References is appendix
                counters = [0] * 8
            continue
        if re.match(r"(?i)^appendix|^supplementary", t) and lvl == 1:
            appendix = True
            out.append(("", t, page, y)); counters = [0] * 8
            continue
        counters[lvl - 1] += 1
        for i in range(lvl, 8):
            counters[i] = 0
        nums = [str(c) for c in counters[:lvl]]
        if appendix:
            nums[0] = chr(ord("A") + counters[0] - 1)
        out.append((".".join(nums), t, page, y))
    return out


def _is_figure_noise(text: str) -> bool:
    lines = [l for l in text.splitlines() if l.strip()]
    if not lines:
        return True
    short = sum(1 for l in lines if len(l.strip()) <= 3)
    return short / len(lines) > 0.5


_VOCAB = None


def _vocab():
    global _VOCAB
    if _VOCAB is None:
        _VOCAB = corpus_vocab("".join(p.get_text() for p in pymupdf.open(ROOT / f"papers/{pid}.pdf"))
                              for pid in PAPERS)
    return _VOCAB


_CAPTION = re.compile(r"\s*Table (\d+)\s*[:.|]")
_NUMERIC = re.compile(r"\d")


def table_regions(paper: str) -> dict[int, list[dict]]:
    """v2 (K §51). Per page, the tables that have a caption: {"n", "bbox", "caption", "header"}.
    - region: PyMuPDF find_tables() outline only (its cell text splits decimals, so it is not used);
    - caption: the "Table N:" block nearest the region, above or below, within 100 pt; each caption is
      matched once, closest pairs first; regions with no caption (figures, layout boxes) are ignored;
    - header: the page's own word lines inside the region, among its first 4 lines, whose share of
      tokens containing a digit is under 50 % (column names, not data rows), grouped into one cell per
      column by x position and joined with " | "."""
    doc = pymupdf.open(ROOT / f"papers/{paper}.pdf")
    vocab = _vocab()
    out = {}
    for pno, page in enumerate(doc, start=1):
        caps = [b for b in page.get_text("blocks") if _CAPTION.match(b[4])]
        tabs = [t.bbox for t in page.find_tables().tables]
        if not caps or not tabs:
            continue
        pairs = []
        for ti, tb in enumerate(tabs):
            for ci, cb in enumerate(caps):
                gap = tb[1] - cb[3] if cb[3] <= tb[1] + 5 else (cb[1] - tb[3] if cb[1] >= tb[3] - 5 else None)
                if gap is not None and gap <= 100:
                    pairs.append((max(gap, 0), ti, ci))
        used_t, used_c, found = set(), set(), []
        for gap, ti, ci in sorted(pairs):
            if ti in used_t or ci in used_c:
                continue
            used_t.add(ti)
            used_c.add(ci)
            tb, cb = tabs[ti], caps[ci]
            words = [w for w in page.get_text("words")
                     if w[0] >= tb[0] - 2 and w[2] <= tb[2] + 2 and w[1] >= tb[1] - 2 and w[3] <= tb[3] + 2]
            lines = {}
            for w in words:
                lines.setdefault(round(w[1] / 3), []).append(w)
            hw = []
            for _, ws in sorted(lines.items())[:4]:
                if sum(bool(_NUMERIC.search(w[4])) for w in ws) / len(ws) < 0.5:
                    hw += ws
            # one cell per column: words that overlap in x (stacked header lines) or sit within 4 pt on a line
            cols = []
            for w in sorted(hw, key=lambda w: w[0]):
                c = next((c for c in cols if w[0] <= c["x1"] + 4 and w[2] >= c["x0"] - 4), None)
                if c is None:
                    cols.append({"x0": w[0], "x1": w[2], "w": [w]})
                else:
                    c["x0"], c["x1"] = min(c["x0"], w[0]), max(c["x1"], w[2])
                    c["w"].append(w)
            head = [" ".join(x[4] for x in sorted(c["w"], key=lambda x: (round(x[1] / 3), x[0])))
                    for c in sorted(cols, key=lambda c: c["x0"])]
            found.append({"n": int(_CAPTION.match(cb[4]).group(1)), "bbox": tuple(tb),
                          "caption_bbox": tuple(cb[:4]),
                          "caption": " ".join(dehyphenate(cb[4], vocab).split()),
                          "header": " | ".join(" ".join(dehyphenate(h, vocab).split()) for h in head)})
        if found:
            out[pno] = found
    return out


def _in_table(regions, pno, x0, y0, x1, y1):
    """Table number a block belongs to (its caption, or overlapping the region), else None."""
    for t in regions.get(pno, []):
        for bx0, by0, bx1, by1 in (t["bbox"], t["caption_bbox"]):
            if x0 < bx1 and x1 > bx0 and y0 < by1 and y1 > by0:
                return t["n"]
    return None


def page_blocks(paper: str, regions: dict | None = None):
    """Yield (page_no, y, text, section_label) for every non-noise text block; with `regions` (v2) a 5th
    item, the table number the block belongs to (or None)."""
    doc = pymupdf.open(ROOT / f"papers/{paper}.pdf")
    vocab = _vocab()
    toc = _numbered_toc(doc)
    for pno, page in enumerate(doc, start=1):
        for x0, y0, x1, y1, text, *_ in page.get_text("blocks"):
            if _is_figure_noise(text):
                continue
            sec = ("0", "Front matter")
            for num, title, tp, ty in toc:
                if (tp, ty) <= (pno, y0 + 10):
                    sec = (num, title)
                else:
                    break
            text = dehyphenate(text, vocab)
            item = (pno, y0, " ".join(text.split()), f"{sec[0]} {sec[1]}".strip())
            yield item if regions is None else item + (_in_table(regions, pno, x0, y0, x1, y1),)


def build_chunks(words_per_chunk: int, overlap: int = 0, chunker: str = "v1") -> list[Chunk]:
    """v1: word windows within a section. v2 (K §51): the SAME windows, and every window that holds part of
    a table starts with that table's caption and header row (K's rule as stated: every such window, even one
    that already holds the caption; the prefix carries the header in column order, the body's own copy may not)."""
    chunks: list[Chunk] = []
    for paper, title in PAPERS.items():
        regions = table_regions(paper) if chunker == "v2" else None
        tinfo = {t["n"]: t for ts in (regions or {}).values() for t in ts}
        # group consecutive blocks by section, keeping page (and v2: table number) of each word
        groups: list[tuple[str, list[tuple]]] = []
        for item in page_blocks(paper, regions):
            pno, _y, text, sec = item[:4]
            tn = item[4] if len(item) > 4 else None
            if sec.startswith(("References", "Bibliography")):
                continue
            if not groups or groups[-1][0] != sec:
                groups.append((sec, []))
            groups[-1][1].extend((w, pno, tn) for w in text.split())
        for sec, words in groups:
            step = max(1, words_per_chunk - overlap)
            for i in range(0, len(words), step):
                win = words[i:i + words_per_chunk]
                if len(win) < 15 and i > 0:   # tiny tail: already covered by overlap/previous
                    continue
                body = " ".join(w for w, _, _ in win)
                prefix, tabs = [], []
                for tn in dict.fromkeys(t for _, _, t in win if t is not None):
                    t = tinfo[tn]
                    tabs.append(tn)
                    prefix.append(f"[Table {tn}, repeated: {t['caption']} | Header: {t['header'] or '(none found)'}]")
                chunks.append(Chunk(
                    id=f"{paper}:{len(chunks)}", paper=paper, title=title, section=sec,
                    page_start=win[0][1], page_end=win[-1][1],
                    text=" ".join(prefix + [body]), tables=tabs or None))
                if i + words_per_chunk >= len(words):
                    break
    return chunks


def save(chunks, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        for c in chunks:
            d = asdict(c)
            if d.get("tables") is None:
                d.pop("tables", None)          # v1 files stay byte-identical
            f.write(json.dumps(d) + "\n")


def load(path: Path) -> list[Chunk]:
    return [Chunk(**json.loads(l)) for l in open(path)]


if __name__ == "__main__":
    import sys
    for size in [int(s) for s in (sys.argv[1:] or ["120", "250", "500"])]:
        cs = build_chunks(size, overlap=size // 5)
        save(cs, ROOT / f"data/chunks_w{size}.jsonl")
        print(size, len(cs), "chunks; e.g.", cs[40].cite(), cs[40].text[:120])
