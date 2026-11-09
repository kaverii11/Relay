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


def page_blocks(paper: str):
    """Yield (page_no, y, text, section_label) for every non-noise text block."""
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
            yield pno, y0, " ".join(text.split()), f"{sec[0]} {sec[1]}".strip()


def build_chunks(words_per_chunk: int, overlap: int = 0) -> list[Chunk]:
    chunks: list[Chunk] = []
    for paper, title in PAPERS.items():
        # group consecutive blocks by section, keeping page of each word
        groups: list[tuple[str, list[tuple[str, int]]]] = []
        for pno, _y, text, sec in page_blocks(paper):
            if sec.startswith(("References", "Bibliography")):
                continue
            if not groups or groups[-1][0] != sec:
                groups.append((sec, []))
            groups[-1][1].extend((w, pno) for w in text.split())
        for sec, words in groups:
            step = max(1, words_per_chunk - overlap)
            for i in range(0, len(words), step):
                win = words[i:i + words_per_chunk]
                if len(win) < 15 and i > 0:   # tiny tail: already covered by overlap/previous
                    continue
                chunks.append(Chunk(
                    id=f"{paper}:{len(chunks)}", paper=paper, title=title, section=sec,
                    page_start=win[0][1], page_end=win[-1][1],
                    text=" ".join(w for w, _ in win)))
                if i + words_per_chunk >= len(words):
                    break
    return chunks


def save(chunks, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        for c in chunks:
            f.write(json.dumps(asdict(c)) + "\n")


def load(path: Path) -> list[Chunk]:
    return [Chunk(**json.loads(l)) for l in open(path)]


if __name__ == "__main__":
    import sys
    for size in [int(s) for s in (sys.argv[1:] or ["120", "250", "500"])]:
        cs = build_chunks(size, overlap=size // 5)
        save(cs, ROOT / f"data/chunks_w{size}.jsonl")
        print(size, len(cs), "chunks; e.g.", cs[40].cite(), cs[40].text[:120])
