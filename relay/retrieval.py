"""Step 2, the retrieval TOOL: BM25 over section-aware chunks, then the cross-encoder.

- rerank=True : cross-encoder scores BM25's top-N and picks the best k.
- rerank=False: BM25's top-k is sent as is; the cross-encoder still scores those k for the gate,
  so the refusal decision uses the same signal in every setting (DECISIONS §12).
- Chunks longer than the cross-encoder's 512-token window are scored in windows, taking the max
  (51% of w500 pairs would otherwise be truncated, measured).
"""
from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from rank_bm25 import BM25Okapi

from relay.config import RetrievalSetting
from relay.ingest import Chunk, build_chunks, load, save

ROOT = Path(__file__).resolve().parents[1]
_tok = lambda s: re.findall(r"\w+", s.lower())  # noqa: E731
_CE = None
_CE_INIT_LOCK = threading.Lock()   # guards loading the model once
_CE_LOCK = threading.Lock()        # serialises inference (one CPU model shared by all workers)
WINDOW_WORDS = 300


def cross_encoder():
    global _CE
    with _CE_INIT_LOCK:
        if _CE is None:
            from sentence_transformers import CrossEncoder
            _CE = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
    return _CE


@dataclass
class Hit:
    chunk: Chunk
    bm25: float
    ce: float


class Retriever:
    def __init__(self, setting: RetrievalSetting):
        self.s = setting
        v2 = getattr(setting, "chunker", "v1") == "v2"
        path = ROOT / f"data/chunks_w{setting.words}{'_v2' if v2 else ''}.jsonl"
        if not path.exists():
            save(build_chunks(setting.words, overlap=setting.words // 5, chunker="v2" if v2 else "v1"), path)
        self.chunks = load(path)
        self.bm = BM25Okapi([_tok(c.text) for c in self.chunks])

    def _ce_scores(self, query: str, chunks: list[Chunk]) -> list[float]:
        pairs, owner = [], []
        for i, c in enumerate(chunks):
            words = c.text.split()
            for j in range(0, max(1, len(words)), WINDOW_WORDS):
                pairs.append((query, " ".join(words[j:j + WINDOW_WORDS + 40])))
                owner.append(i)
                if j + WINDOW_WORDS >= len(words):
                    break
        model = cross_encoder()        # must NOT be called while holding _CE_LOCK (that deadlocked)
        with _CE_LOCK:                 # serialised inference: a real cost under load, measured as ce_ms
            raw = model.predict(pairs, show_progress_bar=False)
        best = [-1e9] * len(chunks)
        for o, sc in zip(owner, raw):
            best[o] = max(best[o], float(sc))
        return best

    def search(self, query: str, k: int | None = None) -> tuple[list[Hit], float, dict]:
        k = k or self.s.k
        t0 = time.perf_counter()
        scores = self.bm.get_scores(_tok(query))
        top = list(np.argsort(-scores)[: self.s.candidates])
        t1 = time.perf_counter()
        if self.s.rerank:
            cand = [self.chunks[i] for i in top]
            ce = self._ce_scores(query, cand)
            order = sorted(range(len(cand)), key=lambda j: -ce[j])[:k]
            hits = [Hit(cand[j], float(scores[top[j]]), ce[j]) for j in order]
            # BM25's own top-k with the scores already computed: the fewer-chunks rung (K §44) sends these
            bm_top = [Hit(cand[j], float(scores[top[j]]), ce[j]) for j in range(min(k, len(cand)))]
        else:
            cand = [self.chunks[i] for i in top[:k]]
            ce = self._ce_scores(query, cand)
            hits = [Hit(c, float(scores[i]), s) for c, i, s in zip(cand, top[:k], ce)]
            bm_top = hits
        t2 = time.perf_counter()
        gate = max(h.ce for h in hits) if hits else -1e9
        return hits, gate, {"bm25_ms": (t1 - t0) * 1000, "ce_ms": (t2 - t1) * 1000, "bm25_top": bm_top}
